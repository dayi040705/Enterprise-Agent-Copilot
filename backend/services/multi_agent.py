"""
Multi-Agent v2 — 并行执行 + 共享状态 + 智能Reviewer + 可追踪

升级点:
  1. asyncio.gather 真正并行执行
  2. SharedState 所有 Agent 读写同一份数据
  3. Reviewer 输出 missing_evidence + next_action, 打回后自动补查
  4. 执行树 trace 可视化
"""
import json, asyncio, hashlib
from dataclasses import dataclass, field, asdict
from typing import TypedDict, AsyncGenerator, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from services.executor import execute as exec_tool, save_memory as exec_save_memory
from services.executor import MCPOrdersParams, QueryAnalyticsParamsV2, QueryListingParams, QuerySyncLogsParams
from services.chroma import client as chroma_client
from services.embedding import embedding_texts

client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
TOOL_TIMEOUT = 15  # 单个工具最多跑 15 秒


async def _exec_with_timeout(name: str, args: dict, dept: str, user_dept: str = "") -> str:
    """工具执行 + 超时 + 异常保护 + 权限校验"""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(exec_tool, name, args, dept, 0, user_dept),
            timeout=TOOL_TIMEOUT
        )
        return result
    except asyncio.TimeoutError:
        return f"[超时] {name} 执行超过 {TOOL_TIMEOUT}s, 已取消。"
    except Exception as e:
        return f"[异常] {name} 执行出错: {type(e).__name__}: {str(e)[:100]}"

# ── 共享状态 ──

class SharedState(TypedDict, total=False):
    question: str
    department: str
    tasks: list
    evidence: dict        # {"diagnostic": [Evidence, ...], ...}
    report: str
    review: dict
    rewrite_count: int
    trace_tree: list


@dataclass
class Evidence:
    """证据原子 — Reporter/Reviewer/Eval 都吃这个结构"""
    agent: str
    tool: str
    content: str
    source: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict: return asdict(self)
    def summary(self) -> str: return f"[{self.agent}/{self.tool}] {self.content[:120]}"


@dataclass
class TraceNode:
    """执行轨迹节点 — 树形结构, 前端渲染用"""
    id: str
    type: str              # "supervisor" | "agent" | "tool" | "reporter" | "reviewer"
    name: str
    parent_id: str = ""
    input: str = ""
    output: str = ""
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""
    children: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["children"] = [c.to_dict() if isinstance(c, TraceNode) else c for c in self.children]
        return d


# ── Trace 存储 (内存) ──
_trace_sessions: dict[str, TraceNode] = {}

def get_session_trace(session_id: str) -> dict | None:
    root = _trace_sessions.get(session_id)
    return root.to_dict() if root else None


@dataclass
class Incident:
    """故障事件 — 解决后存入长期记忆"""
    service: str
    problem: str
    root_cause: str = ""
    solution: str = ""
    time: str = ""
    severity: str = "P2"

    def to_text(self) -> str:
        return (f"服务: {self.service}\n问题: {self.problem}\n"
                f"根因: {self.root_cause}\n解决方案: {self.solution}\n"
                f"时间: {self.time}\n严重程度: {self.severity}")

# ── 故障记忆库 (ChromaDB) ──

_incident_collection = chroma_client.get_or_create_collection(name="agent_incidents")

def save_incident(incident: Incident, department: str) -> str:
    """保存故障事件到长期记忆"""
    doc_id = f"inc_{incident.time.replace(' ', 'T').replace(':', '')}"
    text = incident.to_text()
    vector = embedding_texts([incident.problem])[0]
    _incident_collection.upsert(
        documents=[text], embeddings=[vector],
        metadatas=[{"service": incident.service, "department": department,
                     "time": incident.time, "severity": incident.severity}],
        ids=[doc_id],
    )
    return doc_id

def search_incidents(query: str, department: str, top_k: int = 3) -> list[str]:
    """搜索历史故障事件"""
    try:
        vector = embedding_texts([query])[0]
        r = _incident_collection.query(
            query_embeddings=[vector], n_results=top_k,
            where={"department": department},
            include=["documents", "distances"],
        )
        docs = r.get("documents", [[]])[0]
        dists = r.get("distances", [[]])[0]
        out = []
        for i, (doc, dist) in enumerate(zip(docs, dists)):
            out.append(f"[历史事件 {i+1} | 相似度 {1-dist:.0%}]\n{doc}")
        return out
    except Exception:
        return []

# ── Pydantic Tool Schema ──

class SearchKBInput(BaseModel):
    query: str = Field(..., min_length=1, description="搜索关键词")
    department: str = Field(..., pattern="^(HR|TECH|运营部|客服部|供应链部)$")

class SearchLogsInput(BaseModel):
    service: str = Field(..., pattern="^(user-service|order-service|payment-service|sp-api|inventory-service)$")
    keyword: str = Field(default="")

class SearchMemoryInput(BaseModel):
    query: str = Field(..., min_length=1)
    department: str = Field(..., pattern="^(HR|TECH|运营部|客服部|供应链部)$")

class QueryMySQLInput(BaseModel):
    sql: str = Field(..., min_length=5, max_length=500, description="SELECT 查询语句。可用表: products/orders/order_items/order_reviews/sellers/order_payments/sync_logs")

class QueryAnalyticsInput(BaseModel):
    sql: str = Field(..., min_length=5, max_length=500, description="SELECT 查询语句。查趋势/聚合用。可用表: sales_daily/listing_snapshots/sync_etl_log")

class SearchIncidentsInput(BaseModel):
    query: str = Field(..., min_length=1, description="问题描述, 如'Redis超时'")
    department: str = Field(..., pattern="^(HR|TECH|运营部|客服部|供应链部)$")


def _make_tool(name: str, desc: str, model: type[BaseModel]) -> dict:
    """Pydantic → OpenAI Function Calling JSON Schema"""
    schema = model.model_json_schema()
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {
            "type": "object",
            "properties": schema["properties"],
            "required": schema.get("required", [])
        }
    }}


KNOWLEDGE_TOOLS = [
    _make_tool("search_knowledge_base", "搜索企业知识库", SearchKBInput),
]

DIAGNOSTIC_TOOLS = [
    _make_tool("query_sync_logs", "查数据管道健康度(录入率/失败原因) — 优先用这个!", QuerySyncLogsParams),
    _make_tool("search_logs", "搜GitHub开源社区的真实技术问题/故障案例(外部参考)", SearchLogsInput),
    _make_tool("search_memory", "搜索历史运营经验", SearchMemoryInput),
    _make_tool("search_incidents", "搜索历史事件库(同类问题以前怎么解决的)", SearchIncidentsInput),
]

ACTION_TOOLS = [
    _make_tool("query_orders", "查订单状态。参数:status(delivered/canceled/空=全部),limit(默认10)", MCPOrdersParams),
    _make_tool("query_analytics", "查销量/退款率/库存预警(OLAP预聚合,毫秒级)。参数:metric(top_refund/top_sales/low_stock/trend),limit(默认5)", QueryAnalyticsParamsV2),
    _make_tool("query_listing", "查Listing评分/评价数/健康度。参数:sku(可选),category(可选),limit(默认10)", QueryListingParams),
    _make_tool("query_sync_logs", "查SP-API数据管道同步健康度(录入率/失败原因)。参数:hours(默认24)", QuerySyncLogsParams),
]

# ── 第1处: Agent 任务边界 ──

AGENTS = {
    "knowledge": {
        "name": "Knowledge Agent",
        "system": (
            "你是电商运营知识库专家。只负责搜电商 SOP(售后/广告/Listing/跟卖/库存)。"
            "不负责查数据、不负责查日志。引用来源文件名。"
        ),
        "tools": KNOWLEDGE_TOOLS,
    },
    "diagnostic": {
        "name": "Diagnostic Agent",
        "system": (
            "你是系统诊断专家。工具使用优先级:\n"
            "1. query_sync_logs — 查管道录入率/失败(内部数据,优先)\n"
            "2. search_memory — 搜历史运营异常处理经验(内部)\n"
            "3. search_incidents — 搜历史事件库\n"
            "4. search_logs — 搜GitHub开源社区真实技术案例(外部参考,最后手段)\n"
            "不负责搜知识库文档、不负责查业务数据库。"
        ),
        "tools": DIAGNOSTIC_TOOLS,
    },
    "action": {
        "name": "Action Agent",
        "system": (
            "你是电商数据查询专家。有 4 个参数化工具:\n"
            "query_orders — 查订单状态(status/limit)\n"
            "query_analytics — 查销量/退款率/库存预警(metric/limit)\n"
            "query_listing — 查Listing评分/评价数(sku/category/limit)\n"
            "query_sync_logs — 查数据管道健康度(hours)\n"
            "规则: 先查后答,杜绝编造,标注数据来源。\n"
            "1. 优先用MCP工具(不用写SQL,不会出错)\n"
            "2. MCP不够用时再用自定义SQL\n"
            "3. analytics.sales_daily是预聚合表,查退款率/销量趋势用它,别三表JOIN\n"
            "4. 查完后直接给出答案,不要反复调工具\n"
        ),
        "tools": ACTION_TOOLS,
    },
}

# ── 第2处: Tool Guardrail — 表白名单 ──

TABLE_RULES = {
    "故障|服务|事故|异常|超时|500|报错|ERROR|宕机|排查|日志": ["tickets"],
    "员工|通讯录|电话|邮箱|分机|联系人": ["employees"],
    "请假|假期|年假|病假|事假|婚假": ["leave_records"],
}

def _validate_table(task: str, table: str) -> bool:
    """检查表是否匹配任务类型"""
    import re
    for pattern, allowed in TABLE_RULES.items():
        if re.search(pattern, task):
            return table in allowed
    return True


def _extract_service(task: str) -> str:
    """从任务描述中提取服务名"""
    import re
    for svc in ["user-service", "payment-service", "order-service"]:
        if svc in task: return svc
    return ""


# ── 并行执行 ──

async def _call_specialist(agent_type: str, task: str, dept: str, max_calls: int = 3) -> tuple[list[dict], list]:
    """调一个专业 Agent, 返回 (evidence_items, trace).
       evidence_items: [{"source": "search_logs", "content": "..."}, ...]"""
    agent = AGENTS[agent_type]
    msgs = [
        {"role": "system", "content": f"{agent['system']} 部门: {dept}。"},
        {"role": "user", "content": f"任务: {task}\n用工具获取数据后简洁输出。"},
    ]
    evidence_items, trace = [], []

    for _ in range(max_calls):
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL, messages=msgs, tools=agent["tools"], temperature=0)
        ch = resp.choices[0]

        if ch.message.tool_calls:
            for tc in ch.message.tool_calls:
                try: args = json.loads(tc.function.arguments)
                except json.JSONDecodeError: continue
                if tc.function.name in ("search_incidents", "search_memory"):
                    raw_q = args.get("query", "")
                    svc = _extract_service(task)
                    enhanced = f"服务: {svc} 问题: {raw_q}" if svc else raw_q
                    args["query"] = enhanced  # 注入增强 query
                    if tc.function.name == "search_incidents":
                        r = "\n".join(search_incidents(enhanced, args.get("department", dept))) or "历史事件库中无匹配记录"
                    else:
                        r = exec_tool(tc.function.name, args, dept)
                elif tc.function.name == "query_database" and not _validate_table(task, args.get("table", "")):
                    r = (f"[拒绝] 表 '{args.get('table')}' 与任务'{task[:60]}'不匹配。")
                else:
                    r = await _exec_with_timeout(tc.function.name, args, dept, user_dept=dept)
                evidence_items.append(Evidence(
                    agent=agent_type, tool=tc.function.name,
                    content=r[:500], source=tc.function.name))
                trace.append({"tool": tc.function.name, "args": args, "result": r[:120]})
                am = {"role": "assistant", "content": None,
                      "tool_calls": [{"id": tc.id, "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}}]}
                if hasattr(ch.message, "reasoning_content") and ch.message.reasoning_content:
                    am["reasoning_content"] = ch.message.reasoning_content
                msgs.append(am)
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": r})
        else:
            evidence_items.append(Evidence(
                agent=agent_type, tool="llm_answer",
                content=ch.message.content, source="LLM直接回答"))
            break

    return evidence_items, trace


async def _execute_parallel(state: SharedState, yield_cb=None) -> dict:
    """并行执行, 逐个完成即推状态 (非全部等完)"""
    tasks = state["tasks"]
    dept = state["department"]

    async def run_one(item):
        agent_type = item["agent"]
        task = item["task"]
        evidence_items, trace = await _call_specialist(agent_type, task, dept)
        return agent_type, evidence_items, trace

    # as_completed: 谁先完成就先推状态
    coros = [run_one(t) for t in tasks]
    evidence = state.get("evidence", {})
    trace_nodes = []

    for coro in asyncio.as_completed(coros):
        agent_type, evidence_items, trace = await coro
        if agent_type not in evidence:
            evidence[agent_type] = []
        evidence[agent_type].extend(evidence_items)
        trace_nodes.append({
            "agent": agent_type, "name": AGENTS[agent_type]["name"],
            "items": len(evidence_items), "children": trace,
        })
        # 逐个推状态
        if yield_cb:
            yield_cb(f"{AGENTS[agent_type]['name']} 完成: {len(evidence_items)} 条证据")

    state["evidence"] = evidence
    state["trace_tree"].append({"phase": "execute", "nodes": trace_nodes})
    return evidence


# ── Supervisor ──

async def _supervisor_plan(question: str) -> list[dict]:
    prompt = f"""你是电商运营调度专家。有 3 个 Agent:

- knowledge: 搜电商 SOP 知识库 (售后处理/广告策略/Listing优化/跟卖应对/库存管理)
- diagnostic: 查数据异常 + 搜索历史经验 + 查 sync_logs 数据管道日志
- action: 查电商业务数据库, 有两个数据源:
  🔵 query_mysql — 实时订单/商品: products, orders, order_items, order_reviews, sellers, sync_logs
  🟢 query_analytics — OLAP预聚合(毫秒级): analytics.sales_daily (日销量/退款率/均价), analytics.listing_snapshots

将问题拆为子任务。JSON 数组:
[{{"agent": "knowledge|diagnostic|action", "task": "具体任务描述(含要查哪张表或什么SOP)"}}]

规则:
- 数据查询(退款率/销量) → action, 走 query_analytics 查 sales_daily (预聚合,快)
- SOP查询(退货/广告) → knowledge, 搜知识库
- 复杂诊断(转化率暴跌需排查评分+广告+跟卖) → 拆分给 action+knowledge+diagnostic

问题: {question}
只输出 JSON:"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    text = resp.choices[0].message.content.strip()
    try:
        if "```" in text: text = text.split("```")[1].split("```")[0]
        s, e = text.find("["), text.rfind("]") + 1
        if s >= 0 and e > s: text = text[s:e]
        return json.loads(text)
    except json.JSONDecodeError:
        return [{"agent": "knowledge", "task": question}]


# ── Reporter ──

async def _supervisor_replan(question: str, missing_evidence: list[str]) -> list[dict]:
    """Supervisor: 根据 Reviewer 发现的缺失项, 生成补查任务"""
    missing_text = "\n".join(f"- {m}" for m in missing_evidence)
    prompt = f"""你是电商运营调度专家。Reviewer 审查后发现以下信息缺失:

原始问题: {question}

缺失信息:
{missing_text}

请为每个缺失项生成一个补查任务, 分配给最合适的 Agent:
- knowledge: 搜电商 SOP 知识库
- diagnostic: 查 sync_logs + 历史经验
- action: 查数据(query_mysql查实时/query_analytics查趋势)

输出 JSON 数组:
[{{"agent": "knowledge|diagnostic|action", "task": "具体任务描述"}}]

只输出 JSON:"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    text = resp.choices[0].message.content.strip()
    try:
        if "```" in text: text = text.split("```")[1].split("```")[0]
        s, e = text.find("["), text.rfind("]") + 1
        if s >= 0 and e > s: text = text[s:e]
        return json.loads(text)
    except json.JSONDecodeError:
        return []


async def _reporter(state: SharedState, extra_context: str = "") -> str:
    evidence = state["evidence"]
    # 格式化证据池: 按 Agent → 逐条列出
    parts = []
    for agent_name, items in evidence.items():
        parts.append(f"--- {agent_name} ({len(items)} 条) ---")
        for i, item in enumerate(items):
            parts.append(f"[{i+1}] {item.tool}: {item.content[:300]}")
    summary = "\n".join(parts)
    ctx = f"\n补充要求: {extra_context}" if extra_context else ""

    prompt = f"""根据以下排查结果, 对'{state['question']}'生成报告:{ctx}

## 各Agent收集的证据:
{summary}

## 第一步: 矛盾检测 (生成报告前必须执行)
逐条对比所有证据, 如果两条证据对同一事实的描述矛盾:
  - start/finish_service 返回 "Redis 连接正常" vs search_logs 返回 "Redis timeout 30次"
  → 标为 ⚠️ 证据冲突: 两方分别引用了什么, 可能原因(时间差? 查的范围不同?)
  → 不选边站, 不隐藏矛盾

## 输出格式要求 (必须遵守):

### ⚠️ 证据冲突 (如有)
每条冲突单独一行, 说明矛盾的双方 + 可能的解释。
如果没有冲突, 写 "无"。

### 已确认事实
每条事实单独一行, 后面用 [→ Agent名 / 工具名 / 来源] 标注证据。

### 推测原因
基于证据的推测, 标注置信度(高/中/低)和依据。如果有证据冲突, 给出两种可能 + 各自的依据。

### 待确认 (缺失信息)
列出还需要什么数据才能确认根因。证据冲突项目优先列出。

## 绝对禁止:
- 没有 [→ Agent/工具/来源] 标注的事实声明
- "根因是XXX" 这种确定性结论(除非证据100%证实)
- 在证据矛盾时自行选边站, 隐瞒矛盾
- 报告中出现知识库/日志中不存在的具体数据

只输出报告:"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content


async def _reporter_stream(state: SharedState, extra_context: str = ""):
    """Reporter 流式版 — 逐 token 推送"""
    evidence = state["evidence"]
    parts = []
    for agent_name, items in evidence.items():
        parts.append(f"--- {agent_name} ({len(items)} 条) ---")
        for i, item in enumerate(items):
            parts.append(f"[{i+1}] {item.tool}: {item.content[:300]}")
    summary = "\n".join(parts)
    ctx = f"\n补充要求: {extra_context}" if extra_context else ""

    prompt = f"""根据排查结果生成报告:{ctx}

证据:
{summary}

第一步: 矛盾检测 — 证据之间有矛盾时标 ⚠️ 证据冲突, 不选边。

输出格式:
### ⚠️ 证据冲突 (如有)
### 已确认事实 (直接列出所有查询到的具体数据——SKU/数字/百分比,不能只说"已查询")。每条标注 [→ Agent/工具/来源]
### 推测原因 (标注置信度)
### 待确认 (缺失信息)

重要: 已确认事实部分必须包含查询工具返回的原始数据(SKU ID的前8位、销量数字、退款率百分比、金额)!禁用"已识别""已生成"等抽象描述!

禁止: 证据矛盾时选边站 / 编造数据 / 无来源标注。
只输出报告:"""
    stream = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0, stream=True)
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ── Reviewer v2: 不只打分, 还输出缺失项 ──

async def _reviewer_v2(state: SharedState) -> dict:
    report = state["report"]
    evidence = state["evidence"]
    ev_summary = "\n".join(f"{k}: {v[:200]}" for k, v in evidence.items())

    prompt = f"""你是严格的技术报告审查员。审查以下故障分析报告。

## 收集到的证据:
{ev_summary}

## 报告:
{report[:2000]}

## 评判标准:
- faithfulness: 报告内容是否基于证据(没有编造)? 引用了证据就给高分。
- relevancy: 切题?
- consistency: 证据之间有矛盾时, 报告是否标注了 ⚠️ 冲突而不是隐瞒或选边站?
- passed: faith>=0.5 AND relev>=0.6 (有证据支撑+切题就过)

## 如果未通过:
- missing_evidence: 缺失哪些信息 (只描述缺什么)
- inconsistency: 如果报告在证据矛盾时选边站了, 指出具体矛盾

输出 JSON:
{{"faithfulness":0.0-1.0,"relevancy":0.0-1.0,"passed":true/false,
  "feedback":"一句话","missing_evidence":[],"inconsistency":"(如有)"}}

只输出 JSON:"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0)
    text = resp.choices[0].message.content.strip()
    try:
        if "```" in text: text = text.split("```")[1].split("```")[0]
        s, e = text.find("{"), text.rfind("}") + 1
        if s >= 0 and e > s: text = text[s:e]
        return json.loads(text)
    except json.JSONDecodeError:
        return {"faithfulness": 0.5, "relevancy": 0.5, "passed": False,
                "feedback": "parse error", "missing_evidence": [], "next_action": []}


# ── 主入口: 完整闭环 ──

async def _route_intent(question: str) -> tuple[str, str]:
    """三路 Router: 返回 (route, agent_type)

    knowledge:  问流程/SOP/策略 → Knowledge Agent (search_kb)
    diagnostic: 查数据异常/趋势 → Diagnostic Agent (search_logs/search_memory)
    action:     查具体数据 → Action Agent (query_mysql / query_analytics)
    complex:    多源交叉+诊断报告 → 完整 Multi-Agent
    """
    prompt = f"""你是电商运营系统的路由专家。分析用户意图，只回答一个词。

判断标准(优先级从高到低):

1. action — 单一数据查询，满足任意一条:
   - "退款率最高的是哪个"、"哪个SKU卖得最好"、"最近订单"
   - "查一下XX数据"、"XX有多少"、"XX是什么"
   - 只需要查一张表或一个数据源的简单查询

2. knowledge — 只问流程/SOP/策略:
   - "退货怎么处理"、"广告怎么投放"、"跟卖怎么办"
   - "XX的流程是什么"、"有什么规范"

3. diagnostic — 查数据异常/趋势:
   - 单维度对比: "过去7天销量趋势"、"退款率变化"
   - "有没有异常波动"、"为什么XX下降了"

4. complex — 多源交叉诊断，满足任意一条:
   - 涉及 2 个及以上数据源(数据库+知识库+历史经验)
   - 提到"全面排查"、"诊断报告"、"根因分析"
   - 需要对比多个维度才能得出结论(如"转化率暴跌,排查评分+广告+跟卖")

规则:
- "查退款率最高" → action (单次查询,不是排障)
- "退货流程" → knowledge (SOP)
- "转化率暴跌,全面排查" → complex (需要跨数据源对比)
- "查XX然后分析" → action (数据查询+简单解释)

用户问题: {question}

回答(只一个词):"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=50)
    route = (resp.choices[0].message.content or "").strip().lower()
    if not route or "complex" in route: return ("complex", "")
    if "action" in route: return ("simple", "action")
    if "diagnostic" in route: return ("simple", "diagnostic")
    if "knowledge" in route: return ("simple", "knowledge")
    return ("complex", "")  # 兜底: 默认复杂, 宁可多跑, 不给烂回答


async def multi_agent_chat(question: str, department: str = "TECH",
                           max_iterations: int = 2) -> AsyncGenerator[dict, None]:
    """Router → Simple Agent or Full Multi-Agent"""
    route, agent_type = await _route_intent(question)

    # 简单路由: 单Agent 直接回答
    if route == "simple":
        agent_name = AGENTS[agent_type]["name"]
        yield json.dumps({"type": "status", "data": f"Router→{agent_name}"}, ensure_ascii=False)

        # 如果是 knowledge, 额外做一个简短回答
        evidence_items, _ = await _call_specialist(agent_type, question, department)
        results = [e.summary() for e in evidence_items]

        if results:
            # 用收集到的证据生成简洁回答
            ctx = "\n".join(e.content[:300] for e in evidence_items)
            answer_prompt = f"根据以下证据简洁回答用户问题'{question}'(不超过200字):\n\n{ctx}"
            ans = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": answer_prompt}],
                temperature=0, max_tokens=300)
            answer = ans.choices[0].message.content
        else:
            answer = "未找到相关信息"

        # Trace
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%H:%M:%S"); cid = hashlib.md5(question.encode()).hexdigest()[:12]
        root = TraceNode(id="root", type="user", name=question[:60], input=question, timestamp=ts)
        router = TraceNode(id="router", type="supervisor", name=f"Router → {agent_name}",
                           parent_id="root", timestamp=ts)
        agent = TraceNode(id=f"agent_{agent_type}", type="agent", name=agent_name,
                          parent_id="router", timestamp=ts)
        for i, ev in enumerate(evidence_items):
            agent.children.append(TraceNode(id=f"tool_{i}", type="tool", name=ev.tool,
                parent_id=f"agent_{agent_type}", output=ev.content[:200], timestamp=ts))
        router.children.append(agent); root.children.append(router)
        _trace_sessions[cid] = root

        yield json.dumps({"type": "done", "answer": answer, "session_id": cid}, ensure_ascii=False)
        return

    # 复杂路由: 完整 Multi-Agent
    state: SharedState = {
        "question": question, "department": department,
        "tasks": [], "evidence": {}, "report": "", "review": {},
        "rewrite_count": 0, "trace_tree": [],
    }

    # Phase 1: Supervisor
    state["tasks"] = await _supervisor_plan(question)
    state["trace_tree"].append({"phase": "supervisor", "plan": state["tasks"]})
    yield json.dumps({"type": "plan", "data": [t["task"] for t in state["tasks"]]}, ensure_ascii=False)

    # Phase 2: 并行执行 — 逐个完成就推状态
    yield json.dumps({"type": "status", "data": f"{len(state['tasks'])} 个 Agent 并行执行中..."}, ensure_ascii=False)
    await _execute_parallel(state, yield_cb=lambda msg: None)  # 同步版本不推细节
    yield json.dumps({"type": "status", "data": f"全部完成, 收到证据: {list(state['evidence'].keys())}"}, ensure_ascii=False)

    # Phase 3-5: Reporter → Reviewer → 自动补查闭环
    for iteration in range(max_iterations):
        # Reporter (流式逐 token)
        yield json.dumps({"type": "status", "data": "Reporter: 生成报告..."}, ensure_ascii=False)
        report_text = ""
        async for token in _reporter_stream(state):
            report_text += token
            yield json.dumps({"type": "token", "data": token}, ensure_ascii=False)
        state["report"] = report_text

        # Reviewer
        review = await _reviewer_v2(state)
        state["review"] = review
        state["trace_tree"].append({"phase": "reviewer", "review": review})

        if review.get("passed", False):
            yield json.dumps({"type": "status", "data": f"Reviewer: 通过 (faith={review['faithfulness']:.0%})"}, ensure_ascii=False)
            break

        # 不通过 → Reviewer 告诉 Supervisor 缺什么 → Supervisor 生成补查任务
        missing = review.get("missing_evidence", [])

        if missing and iteration < max_iterations - 1:
            yield json.dumps({"type": "status",
                "data": f"Reviewer→Supervisor: 发现 {len(missing)} 个缺失项, Supervisor 规划补查..."}, ensure_ascii=False)

            # Supervisor 根据缺失项规划补查任务
            replan = await _supervisor_replan(state["question"], missing)
            if replan:
                state["tasks"].extend(replan)
                await _execute_parallel(state)
                yield json.dumps({"type": "status",
                    "data": f"补查完成, 新增证据: {list(state['evidence'].keys())}"}, ensure_ascii=False)
        else:
            yield json.dumps({"type": "status", "data": "达最大迭代, 输出当前版本"}, ensure_ascii=False)
            break

    # ── 构建 TraceNode 树 ──
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%H:%M:%S")

    root = TraceNode(id="root", type="user", name=question[:60], input=question, timestamp=ts)

    # Supervisor
    sup = TraceNode(id="supervisor", type="supervisor", name="Supervisor",
                    parent_id="root", output=json.dumps(state["tasks"], ensure_ascii=False),
                    timestamp=ts)
    root.children.append(sup)

    # Execute phase: 从 trace_tree 取 tool args (不是从 evidence 取 content)
    for node in state.get("trace_tree", []):
        if node.get("phase") == "execute":
            for tn in node.get("nodes", []):
                agent_name = tn["agent"]
                agent_node = TraceNode(
                    id=f"agent_{agent_name}", type="agent",
                    name=AGENTS.get(agent_name, {}).get("name", agent_name),
                    parent_id="supervisor", timestamp=ts)
                for child in tn.get("children", []):
                    tool_node = TraceNode(
                        id=f"tool_{agent_name}_{child['tool']}", type="tool",
                        name=child["tool"],
                        parent_id=f"agent_{agent_name}",
                        input=json.dumps(child.get("args", {}), ensure_ascii=False),
                        output=(child.get("result") or "")[:300],
                        timestamp=ts)
                    agent_node.children.append(tool_node)
                sup.children.append(agent_node)
            break

    # Reporter
    rep = TraceNode(id="reporter", type="reporter", name="Reporter",
                    parent_id="supervisor", output=state["report"][:300], timestamp=ts)
    sup.children.append(rep)

    # Reviewer
    rv = state.get("review", {})
    rev = TraceNode(id="reviewer", type="reviewer", name="Reviewer",
                    parent_id="reporter",
                    output=json.dumps({"faithfulness": rv.get("faithfulness", 0),
                                       "relevancy": rv.get("relevancy", 0),
                                       "passed": rv.get("passed"),
                                       "missing": rv.get("missing_evidence", [])[:3]},
                                      ensure_ascii=False),
                    timestamp=ts)
    rep.children.append(rev)

    # 保存到 session 存储
    cid = hashlib.md5(question.encode()).hexdigest()[:12]
    _trace_sessions[cid] = root

    # 自动存入故障记忆 (Reviewer 通过后才存)
    review = state.get("review", {})
    if review.get("passed"):
        try:
            from datetime import datetime
            service = ""
            if "user-service" in question: service = "user-service"
            elif "payment-service" in question: service = "payment-service"
            elif "order-service" in question: service = "order-service"
            inc = Incident(service=service, problem=question[:200],
                           root_cause="", solution=state["report"][:500],
                           time=datetime.now().strftime("%Y-%m-%d %H:%M"), severity="P1")
            save_incident(inc, department)
        except Exception: pass

    # 最终输出
    trace_summary = _format_trace(state["trace_tree"])
    yield json.dumps({"type": "done", "answer": state["report"],
                       "plan": [t["task"] for t in state["tasks"]],
                       "review": state["review"],
                       "trace": trace_summary,
                       "session_id": cid}, ensure_ascii=False)


def _format_trace(trace_tree: list) -> list:
    """格式化执行树为可读结构"""
    lines = []
    for node in trace_tree:
        phase = node.get("phase", "")
        if phase == "supervisor":
            lines.append("Supervisor")
            for t in node.get("plan", []):
                lines.append(f"  |-- {t['agent']}: {t['task'][:60]}")
        elif phase == "execute":
            for n in node.get("nodes", []):
                lines.append(f"  {n['name']}")
                for child in n.get("children", []):
                    lines.append(f"    |-- {child['tool']}({json.dumps(child.get('args',{}), ensure_ascii=False)[:40]})")
        elif phase == "reviewer":
            r = node.get("review", {})
            lines.append(f"Reviewer: passed={r.get('passed')}, faith={r.get('faithfulness',0):.0%}")
    return lines
