"""
Executor 模块 — 工具注册、参数校验、执行路由

职责:
  1. 定义每个工具的参数 Schema (Pydantic)
  2. 注册工具实现函数
  3. 统一入口: execute(name, args, **ctx) → result

添加新工具只需两步:
  1. 在 TOOL_REGISTRY 注册 (Pydantic Model + 执行函数)
  2. 在 TOOLS 列表加 OpenAI 格式的工具描述
"""
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError
from services.hybrid import hybrid_search
from services.chroma import client as chroma_client
from services.embedding import embedding_texts
from services.database import _query_oltp, _query_olap


# ============================================================
# 参数校验模型
# ============================================================

class SearchKBParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., pattern="^(HR|TECH|运营部|客服部|供应链部)$")

class SearchLogsParams(BaseModel):
    service: str = Field(..., pattern="^(user-service|order-service|payment-service|sp-api|inventory-service)$")
    keyword: str = Field(default="", max_length=50)

class QueryMySQLParams(BaseModel):
    sql: str = Field(..., min_length=5, max_length=500,
                     description="SQL 查询语句 (SELECT only). 可用表见 schema 描述")

class QueryAnalyticsParams(BaseModel):
    sql: str = Field(..., min_length=5, max_length=500,
                     description="SQL 查询语句 (SELECT only). 可用表: sales_daily/listing_snapshots/sync_etl_log")

class SearchMemoryParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., pattern="^(HR|TECH|运营部|客服部|供应链部)$")


# ============================================================
# 长期记忆存储
# ============================================================

_memory_collection = chroma_client.get_or_create_collection(name="agent_memory")


def save_memory(problem: str, solution: str, department: str) -> str | None:
    """存入长期记忆 (带去重+质量过滤)"""
    if len(solution) < 80:
        return None
    skip = ["未找到", "已达上限", "无法完成", "请换个方式"]
    if any(kw in solution for kw in skip):
        return None
    # 去重
    try:
        existing = _search_memory_raw(problem, department, top_k=1)
        if existing and existing[0][1] > 0.9:
            return None
    except Exception:
        pass

    doc_id = f"mem_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    vector = embedding_texts([problem])[0]
    _memory_collection.add(
        documents=[f"问题: {problem}\n解决方案: {solution[:500]}"],
        embeddings=[vector],
        metadatas=[{
            "problem": problem[:200], "department": department,
            "time": datetime.now().isoformat(),
            "expire_at": int((datetime.now().replace(year=datetime.now().year+1)).timestamp()),
        }],
        ids=[doc_id],
    )
    return doc_id


def _search_memory_raw(query: str, department: str, top_k: int = 3):
    """
    搜索长期记忆, 自动过滤过期记录。
    过期条件: expire_at 已过当前时间 (ChromaDB $gte 过滤)。
    """
    vector = embedding_texts([query])[0]
    r = _memory_collection.query(
        query_embeddings=[vector], n_results=top_k * 2,  # 多取一些, Python 层过滤
        where={"department": department},
        include=["documents", "distances", "metadatas"],
    )
    docs = r.get("documents", [[]])[0]
    dists = r.get("distances", [[]])[0]
    metas = r.get("metadatas", [[]])[0]

    # 经验越旧, 相似度分数轻微降权 (6个月后的开始衰减)
    now = datetime.now()
    result = []
    for i, (doc, dist, meta) in enumerate(zip(docs, dists, metas)):
        if meta and "expire_at" in meta:
            try:
                exp = meta["expire_at"]
                if isinstance(exp, (int, float)) and exp > 1000000:
                    expire_dt = datetime.fromtimestamp(float(exp))
                elif isinstance(exp, str):
                    expire_dt = datetime.fromisoformat(exp)
                else:
                    result.append((doc, dist)); continue
                if (expire_dt - now).days <= 0:
                    continue  # 过期, 跳过
                if (expire_dt - now).days < 180:
                    doc += " [较旧,仅供参考]"
            except Exception:
                pass
        result.append((doc, dist))
        if len(result) >= top_k: break
    return result


# ============================================================
# 工具实现
# ============================================================

def _execute_search_kb(query: str, department: str = "HR",
                       empty_streak: int = 0, **kwargs) -> str:
    if empty_streak >= 3:
        return "[建议停止搜索] 连续多次空搜索, 该部门知识库中可能不存在相关内容。请直接给出回答。"
    results = hybrid_search(query.strip(), department, top_k=3)
    if not results:
        return (f"[未找到] 搜索 '{query}' 无结果 (连续空搜索 {empty_streak+1}/3)。"
                f"建议换完全不同的话题方向。")
    out = []
    for i, r in enumerate(results):
        src = r["metadata"].get("filename", "未知")
        page = r["metadata"].get("page", 0)
        out.append(f"[{i+1}] 来源:{src} (第{page}页)\n{r['text'][:300]}")
    return "\n\n".join(out)


def _execute_search_logs(service: str, keyword: str = "", **kwargs) -> str:
    # === 电商服务日志 (优先) ===
    svc_map = {
        "payment-service": "payment-service.log",
        "order-service": "order-service.log",
        "inventory-service": "inventory-service.log",
        "sp-api": "sp-api.log",
        "user-service": "sp-api.log",
    }
    log_file_name = svc_map.get(service, f"{service}.log")

    # === 真实数据源: GitHub Issues API (外部参考) ===
    try:
        import requests
        query = f"{service} {keyword}".strip()
        resp = requests.get(
            "https://api.github.com/search/issues",
            params={"q": query, "per_page": 5, "sort": "created", "order": "desc"},
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if not items:
                return (f"[GitHub Issues] 未找到与 '{query}' 相关的 issue。"
                        f"建议换关键词重试或查看其他数据源。")
            lines = [f"GitHub Issues: 搜索 '{query}', 共 {resp.json().get('total_count', 0)} 条, 展示前 5:"]
            for i, iss in enumerate(items):
                repo = iss.get("repository_url", "").split("/")[-1] if "repository_url" in iss else "unknown"
                lines.append(
                    f"[{i+1}] [{repo}] {iss['title']} "
                    f"| 状态:{iss['state']} | 创建:{iss['created_at'][:10]} | "
                    f"标签:{','.join(l['name'] for l in iss.get('labels', [])) or '无'}"
                )
            return "\n".join(lines)
        if resp.status_code == 403:
            return "[GitHub API 限流] 请稍后重试。本地 mock 数据可作为备用。"
    except Exception:
        pass  # API 挂了 → fallback 到本地 mock

    # === Fallback: 本地电商服务日志 (基于真实订单数据) ===
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_file = log_dir / log_file_name
    if not log_file.exists():
        return f"[错误] 日志文件 {service}.log 不存在, 且 GitHub API 不可用。"
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if keyword.strip():
        kw = keyword.strip().lower()
        filtered = [l for l in lines if kw in l.lower()]
    else:
        filtered = lines
    if not filtered:
        return (f"在 {service} 中未找到包含 '{keyword}' 的记录。"
                f"建议搜索 'ERROR' 查看所有错误。")
    err = sum(1 for l in filtered if "ERROR" in l)
    warn = sum(1 for l in filtered if "WARN" in l)
    return (f"{service} ({keyword or '全部'}): 共 {len(filtered)} 条, "
            f"ERROR {err} 条, WARN {warn} 条\n\n" + "".join(filtered[-20:]))


def _execute_search_memory(query: str, department: str = "HR", **kwargs) -> str:
    try:
        results = _search_memory_raw(query, department)
        if not results:
            return f"历史经验库中未找到与 '{query}' 相关的记录。"
        out = []
        for i, (doc, dist) in enumerate(results):
            out.append(f"[历史经验 {i+1} | 相似度 {1-dist:.0%}]\n{doc[:400]}")
        return "\n\n".join(out)
    except Exception as e:
        return f"[长期记忆异常] {e}"


def _execute_query_mysql(sql: str, **kwargs) -> str:
    """OLTP 查询 — 实时交易数据 (products/orders/reviews 等)"""
    # 安全检查: 只允许 SELECT
    clean = sql.strip()
    if not clean.upper().startswith("SELECT"):
        return "[拒绝] query_mysql 只允许 SELECT 查询"
    return _query_oltp(clean)


def _execute_query_analytics(sql: str, **kwargs) -> str:
    """OLAP 查询 — 预聚合趋势数据 (sales_daily 等)"""
    clean = sql.strip()
    if not clean.upper().startswith("SELECT"):
        return "[拒绝] query_analytics 只允许 SELECT 查询"
    return _query_olap(clean)


# ============================================================
# 工具注册表
# ============================================================

# ── 电商参数化工具 ──

class QueryAnalyticsParamsV2(BaseModel):
    metric: str = Field(default="top_refund", pattern="^(top_refund|top_sales|low_stock|trend)$")
    limit: int = Field(default=5, ge=1, le=20)

class QueryListingParams(BaseModel):
    sku: str = Field(default="")
    category: str = Field(default="")
    limit: int = Field(default=10, ge=1, le=20)

class QuerySyncLogsParams(BaseModel):
    hours: int = Field(default=24, ge=1, le=168)


def _execute_analytics_v2(metric: str = "top_refund", limit: int = 5, **kwargs) -> str:
    """参数化 analytics 查询 — 所有日期以数据实际最大日期为准"""
    if metric == "top_refund":
        return _query_olap(f"""
            WITH latest AS (SELECT MAX(date) as max_d FROM analytics.sales_daily)
            SELECT sku, SUM(units_sold) as sold, AVG(refund_rate) as rr
            FROM analytics.sales_daily
            WHERE date > DATE_SUB((SELECT max_d FROM latest), INTERVAL 90 DAY)
            GROUP BY sku HAVING sold > 10
            ORDER BY rr DESC LIMIT {limit}
        """)
    elif metric == "top_sales":
        return _query_olap(f"""
            WITH latest AS (SELECT MAX(date) as max_d FROM analytics.sales_daily)
            SELECT sku, SUM(units_sold) as sold, SUM(revenue) as rev
            FROM analytics.sales_daily
            WHERE date > DATE_SUB((SELECT max_d FROM latest), INTERVAL 30 DAY)
            GROUP BY sku ORDER BY sold DESC LIMIT {limit}
        """)
    elif metric == "low_stock":
        return _query_olap(f"""
            WITH max_date AS (SELECT MAX(date) as max_d FROM analytics.sales_daily)
            SELECT sku,
                   SUM(CASE WHEN date > DATE_SUB((SELECT max_d FROM max_date), INTERVAL 7 DAY) THEN units_sold ELSE 0 END) as recent,
                   SUM(CASE WHEN date > DATE_SUB((SELECT max_d FROM max_date), INTERVAL 30 DAY) THEN units_sold ELSE 0 END) as month
            FROM analytics.sales_daily
            GROUP BY sku HAVING month > 5 AND recent = 0
            LIMIT {limit}
        """)
    elif metric == "trend":
        return _query_olap(f"""
            WITH latest AS (SELECT MAX(date) as max_d FROM analytics.sales_daily)
            SELECT date, SUM(units_sold) as sold, SUM(revenue) as rev, AVG(refund_rate) as rr
            FROM analytics.sales_daily
            WHERE date > DATE_SUB((SELECT max_d FROM latest), INTERVAL 30 DAY)
            GROUP BY date ORDER BY date DESC LIMIT {limit}
        """)


def _execute_listing(sku: str = "", category: str = "", limit: int = 10, **kwargs) -> str:
    """查 Listing 评分/评价数"""
    from services.mcp_client import call_mcp_tool
    return call_mcp_tool("query_listing_health", {"sku": sku, "category": category, "limit": limit})


def _execute_sync_logs(hours: int = 24, **kwargs) -> str:
    """查数据管道健康度"""
    from services.mcp_client import call_mcp_tool
    return call_mcp_tool("query_sync_health", {"hours": hours})


# MCP 工具调用代理
def _execute_mcp_orders(status: str = "", limit: int = 10, **kwargs) -> str:
    from services.mcp_client import call_mcp_tool
    return call_mcp_tool("query_orders", {"status": status, "limit": limit})


def _execute_mcp_analytics(query: str = "", limit: int = 5, **kwargs) -> str:
    from services.mcp_client import call_mcp_tool
    if "退款" in query or "refund" in query.lower():
        return call_mcp_tool("query_analytics_top_refund", {"limit": limit})
    return call_mcp_tool("query_analytics_sales", {"sku": query, "limit": limit})


class MCPOrdersParams(BaseModel):
    status: str = Field(default="", description="订单状态: delivered/canceled")
    limit: int = Field(default=10, ge=1, le=50, description="返回条数")

class MCPAnalyticsParams(BaseModel):
    query: str = Field(default="", description="SKU 或 查询关键词")
    limit: int = Field(default=5, ge=1, le=20)


TOOL_REGISTRY = {
    # 知识库 + 日志 + 记忆
    "search_knowledge_base": {"model": SearchKBParams, "func": _execute_search_kb},
    "search_logs":           {"model": SearchLogsParams, "func": _execute_search_logs},
    "search_memory":         {"model": SearchMemoryParams, "func": _execute_search_memory},
    # 电商数据查询 (参数化,不用写SQL)
    "query_orders":          {"model": MCPOrdersParams, "func": _execute_mcp_orders},
    "query_analytics":       {"model": QueryAnalyticsParamsV2, "func": _execute_analytics_v2},
    "query_listing":         {"model": QueryListingParams, "func": _execute_listing},
    "query_sync_logs":       {"model": QuerySyncLogsParams, "func": _execute_sync_logs},
}


# ============================================================
# 统一执行入口
# ============================================================

def execute(name: str, raw_args: dict, department: str = "HR",
            empty_streak: int = 0, user_dept: str = "") -> str:
    """
    执行一个工具。

    参数:
      name:         工具名
      raw_args:     LLM 传来的原始参数
      department:   默认部门
      empty_streak: 连续空搜索计数
      user_dept:    用户实际部门 (权限校验, 空则跳过)

    返回:
      工具执行结果字符串
    """
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return f"[错误] 未知工具: {name}"

    model = entry["model"]
    func = entry["func"]

    # Pydantic 参数校验
    try:
        validated = model(**raw_args)
        args = validated.model_dump()
    except ValidationError as e:
        errors = []
        for err in e.errors():
            field = ".".join(str(x) for x in err["loc"])
            errors.append(f"{field}: {err['msg']}")
        return f"[参数校验失败] {name}: {'; '.join(errors)}。请修正后重试。"

    # 部门权限校验: 非 admin 用户只能访问自己部门
    if user_dept and user_dept != "ADMIN":
        req_dept = args.get("department") or args.get("dept", "")
        if req_dept and req_dept != user_dept:
            return (f"[权限拒绝] 您所属部门是 {user_dept}, "
                    f"无权访问 {req_dept} 部门的数据。")

    # 注入上下文参数
    args["department"] = args.get("department", department)
    args["empty_streak"] = args.get("empty_streak", empty_streak)

    # 执行
    try:
        return func(**args)
    except Exception as e:
        return (f"[工具执行异常] {name}: {type(e).__name__}: {str(e)[:200]}。"
                f"请换其他方式处理。")
