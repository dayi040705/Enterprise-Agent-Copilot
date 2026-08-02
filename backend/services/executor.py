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
from services.database import query_table


# ============================================================
# 参数校验模型
# ============================================================

class SearchKBParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., pattern="^(HR|TECH)$")

class SearchLogsParams(BaseModel):
    service: str = Field(..., pattern="^(user-service|order-service|payment-service)$")
    keyword: str = Field(default="", max_length=50)

class QueryDBParams(BaseModel):
    table: str = Field(..., pattern="^(employees|tickets|leave_records)$",
                       description="表名: employees / tickets / leave_records")
    name: str = Field(default="", max_length=50, description="员工姓名")
    dept: str = Field(default="", max_length=50, description="部门: HR / TECH / ADMIN")
    status: str = Field(default="", max_length=20, description="工单状态: 已解决 / 处理中 / 待审批")

class SearchMemoryParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    department: str = Field(..., pattern="^(HR|TECH)$")


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
            "expire_at": datetime.now().replace(year=datetime.now().year+1).isoformat(),
        }],
        ids=[doc_id],
    )
    return doc_id


def _search_memory_raw(query: str, department: str, top_k: int = 3):
    vector = embedding_texts([query])[0]
    r = _memory_collection.query(
        query_embeddings=[vector], n_results=top_k,
        where={"department": department},
        include=["documents", "distances"],
    )
    return list(zip(r.get("documents", [[]])[0], r.get("distances", [[]])[0]))


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
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_file = log_dir / f"{service}.log"
    if not log_file.exists():
        return f"[错误] 日志文件 {service}.log 不存在。"
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


def _execute_query_db(table: str, name: str = "", dept: str = "",
                      status: str = "", **kwargs) -> str:
    """查询企业业务数据库 — 员工/工单/请假记录"""
    filters = {}
    if name: filters["name"] = name
    if dept: filters["dept"] = dept
    if status: filters["status"] = status

    try:
        result = query_table(table, filters)
        rows = result["rows"]
        if not rows:
            return (f"表 {table} 中未找到匹配记录。"
                    f"可用表: employees(员工) / tickets(工单) / leave_records(请假)")
        # 格式化输出
        lines = [f"[{table}] 共 {result['total']} 条"]
        for row in rows[:10]:  # 最多10条
            line = " | ".join(f"{k}:{v}" for k, v in row.items())
            lines.append(line[:500])
        return "\n".join(lines)
    except Exception as e:
        return f"[数据库查询异常] {e}"


# ============================================================
# 工具注册表
# ============================================================

TOOL_REGISTRY = {
    "search_knowledge_base": {"model": SearchKBParams, "func": _execute_search_kb},
    "search_logs":           {"model": SearchLogsParams, "func": _execute_search_logs},
    "search_memory":         {"model": SearchMemoryParams, "func": _execute_search_memory},
    "query_database":        {"model": QueryDBParams, "func": _execute_query_db},
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
