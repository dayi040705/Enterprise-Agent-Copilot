"""
LangGraph 状态图 — Agent 推理流程编排

节点:
  call_llm       → 调 DeepSeek, 传 tools
  execute_tools  → 调 executor 执行工具
  (路由器)       → 有 tool_call? 继续 / 没了? 结束

面试金句:
  "手写 ReAct 理解原理后, 用 LangGraph 重构为状态图,
   实现了节点/边/条件路由的清晰分离, 并支持断点恢复。"
"""
import json, hashlib
import operator
from typing import TypedDict, Annotated, Literal, Sequence
from openai import AsyncOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from services.agent import TOOLS
from services.executor import execute as exec_tool

client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com",
                     timeout=120, max_retries=2)


# ── State 定义 ──

class GraphState(TypedDict):
    messages: Annotated[list, operator.add]  # 追加, 不覆盖!
    department: str
    total_calls: int
    empty_streak: int
    final_answer: str


# ── Node 1: 调 LLM (流式, token 实时推送) ──

async def call_llm_node(state: GraphState) -> dict:
    """调 LLM — 非流式, 一次返回完整结果"""
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=state["messages"],
        tools=TOOLS,
        temperature=0,
    )
    choice = resp.choices[0]

    if choice.message.tool_calls:
        new_msgs = [{
            "role": "assistant", "content": None,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in choice.message.tool_calls
            ]
        }]
        return {"messages": new_msgs}
    else:
        new_msgs = [{"role": "assistant", "content": choice.message.content}]
        return {"messages": new_msgs, "final_answer": choice.message.content}


# ── Node 2: 执行工具 ──

async def execute_tools_node(state: GraphState) -> dict:
    """解析 tool_calls, 逐个执行, 结果追加到 messages"""
    last_msg = state["messages"][-1]
    tool_calls = last_msg.get("tool_calls", [])

    results = []
    calls = state.get("total_calls", 0)
    streak = state.get("empty_streak", 0)

    for tc in tool_calls:
        calls += 1
        if calls > 6:
            results.append({"role": "tool", "tool_call_id": tc["id"], "content": "[达上限]"})
            continue

        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            continue

        result = exec_tool(name, args, state["department"], streak)
        if name == "search_knowledge_base":
            if "建议停止" in result: streak = 99
            elif "未找到" in result: streak += 1
            else: streak = 0

        results.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

    return {"messages": results, "total_calls": calls, "empty_streak": streak}


# ── Router: 决定继续还是结束 ──

def should_continue(state: GraphState) -> Literal["tools", "__end__"]:
    """最后一个 assistant 消息有 tool_calls? → 执行工具; 没有? → 结束"""
    last = state["messages"][-1]
    if last.get("tool_calls"):
        return "tools"
    return "__end__"


# ── 构建 Graph ──

def build_agent_graph():
    """构建 Agent 状态图 (可复用)"""
    workflow = StateGraph(GraphState)

    workflow.add_node("call_llm", call_llm_node)
    workflow.add_node("execute_tools", execute_tools_node)

    workflow.set_entry_point("call_llm")

    workflow.add_conditional_edges(
        "call_llm",
        should_continue,
        {"tools": "execute_tools", "__end__": END}
    )
    workflow.add_edge("execute_tools", "call_llm")

    # Checkpoint: 断点恢复用 (内存版, 后续可换 SQLite)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


agent_graph = build_agent_graph()


# ── 对外接口 ──

def _build_initial(department: str, user_message: str, system_extra: str = ""):
    """构建初始状态"""
    base = f"""你是企业运维 Agent。必须遵守以下规则:

1. 【强制使用工具】回答前必须先调用工具获取真实数据。禁止凭记忆瞎编。
2. 【引用来源】每条信息都要注明来自哪个工具/文件/日志。
3. 【多次搜索】一次搜不够就换关键词再搜, 不要轻易放弃。
4. 【具体 > 笼统】"张三 2026年6月15日请了1天病假" 比 "张三有请假记录" 好100倍。
5. 【部门: {department}】只搜本部门数据。"""
    if system_extra:
        base += f"\n{system_extra}"
    return {
        "messages": [
            {"role": "system", "content": base},
            {"role": "user", "content": user_message},
        ],
        "department": department,
        "total_calls": 0,
        "empty_streak": 0,
        "final_answer": "",
    }


async def _gen_plan(user_message: str, department: str) -> list[str]:
    """生成 Planner 执行计划"""
    from services.agent import TOOLS
    tools_desc = ", ".join(t["function"]["name"] for t in TOOLS)
    prompt = f"可用工具: {tools_desc}\n拆为3-5步, 每行一步。问题: {user_message}\n只输出步骤:"
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    steps = []
    for line in resp.choices[0].message.content.strip().split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith("-")):
            c = line.lstrip("0123456789. -、)")
            if len(c) > 5: steps.append(c)
    return steps if steps else [user_message]


# ── ReAct (阻塞) ──

async def run_agent(user_message: str, department: str = "HR",
                    conversation_id: str = "") -> dict:
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]
    config = {"configurable": {"thread_id": cid}}
    existing = await agent_graph.aget_state(config)

    if existing.values:
        initial = {"messages": [{"role": "user", "content": user_message}]}
    else:
        initial = _build_initial(department, user_message)

    final = await agent_graph.ainvoke(initial, config)
    return {"answer": final.get("final_answer", ""), "conversation_id": cid,
            "total_calls": final.get("total_calls", 0)}


# ── ReAct (流式) ──

async def run_agent_stream(user_message: str, department: str = "HR",
                           conversation_id: str = ""):
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]
    config = {"configurable": {"thread_id": cid}}

    existing = await agent_graph.aget_state(config)
    initial = ({"messages": [{"role": "user", "content": user_message}]}
               if existing.values else _build_initial(department, user_message))

    async for event in agent_graph.astream(initial, config, stream_mode="values"):
        if event.get("final_answer"):
            yield json.dumps({"type": "done", "answer": event["final_answer"],
                              "conversation_id": cid}, ensure_ascii=False)
            return

    yield json.dumps({"type": "done", "answer": "",
                      "conversation_id": cid}, ensure_ascii=False)


# ── ReAct (真正 Token 流式) ──

async def run_agent_stream_tokens(user_message: str, department: str = "HR",
                                  conversation_id: str = "", max_calls: int = 8):
    """逐 token 流式 + Analyzer 闭环 + 去重"""
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]
    config = {"configurable": {"thread_id": cid}}

    existing = await agent_graph.aget_state(config)
    if existing.values:
        history = existing.values.get("messages", [])
        # Agent不是聊天机器人: 只保留上一轮的最终问答, 不保留中间工具调用
        slim = [m for m in history if m.get("role") in ("system", "user", "assistant") and not m.get("tool_calls")]
        msgs = slim[-6:] + [{"role": "user", "content": user_message}]
    else:
        msgs = [
            {"role": "system", "content": f"你是电商运营分析 Agent。核心规则: ①先调工具查数据 ②回答时每条事实必须标注来源[SOP文件名/数据源/具体的数字] ③不标注来源=不合格 ④数据够了就直接回答,最多调5次工具。部门: {department}。"},
            {"role": "user", "content": user_message},
        ]

    calls, streak = 0, 0
    useless_streak = 0  # 连续无效调用计数
    seen_calls: set[str] = set()
    full_answer = ""
    analyzer_rounds = 0
    start_len = len(msgs)  # 本轮新增消息的起点 (会话状态只追加新消息)

    for _ in range(max_calls):
        # 条件4: 达到上限 → 强制输出
        if calls >= max_calls:
            full_answer = "[已达上限] 基于已有信息: " + (full_answer or "未能收集到足够数据,请联系人工处理")
            break

        # 条件3: 达到70%配额 + 已有有效数据 → 收尾
        if calls >= max_calls * 0.7 and useless_streak >= 1 and full_answer:
            full_answer = "[已达70%配额] " + full_answer
            break

        # 条件2: 连续2次无新信息 + 有数据 → 收尾
        if useless_streak >= 2 and full_answer:
            full_answer = "[连续无新信息] " + full_answer
            break

        try:
            stream = await client.chat.completions.create(
                model=DEEPSEEK_MODEL, messages=msgs, tools=TOOLS,
                temperature=0, stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as e:
            # 建连失败 (网络/限流/API异常) — 推状态后优雅收尾, 不炸断 SSE
            yield json.dumps({"type": "status",
                "data": f"LLM 调用失败 ({type(e).__name__}), 结束本轮"}, ensure_ascii=False)
            break

        content = ""
        tool_calls_acc: dict[int, dict] = {}

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta: continue
                if delta.content:
                    content += delta.content
                    yield json.dumps({"type": "token", "data": delta.content}, ensure_ascii=False)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": tc.id or "", "function": {"name": "", "arguments": ""}}
                        if tc.id: tool_calls_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name: tool_calls_acc[idx]["function"]["name"] += tc.function.name
                            if tc.function.arguments: tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments
        except Exception as e:
            # 流中途断开 (API 抖动/连接重置) — 保留已生成部分, 优雅收尾
            yield json.dumps({"type": "status",
                "data": f"流式输出中断 ({type(e).__name__}), 返回已生成部分"}, ensure_ascii=False)
            if content:
                full_answer = content
            break

        if tool_calls_acc:
            tool_list = []
            for idx in sorted(tool_calls_acc.keys()):
                tc = tool_calls_acc[idx]
                tool_list.append({
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["function"]["name"],
                                 "arguments": tc["function"]["arguments"]}
                })
            msgs.append({"role": "assistant", "content": None, "tool_calls": tool_list})

            tool_results_summary = []

            for tc in tool_list:
                calls += 1
                name = tc["function"]["name"]
                try: args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError: continue

                # 去重
                call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                if call_key in seen_calls:
                    useless_streak += 1
                    msgs.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": "[跳过] 相同工具+参数已调用过, 请换方式或直接回答。"})
                    continue
                seen_calls.add(call_key)

                yield json.dumps({"type": "tool_call", "tool": name, "args": args}, ensure_ascii=False)
                result = exec_tool(name, args, department, streak)
                # 追踪无效调用
                if "未找到" in result or "无结果" in result or "异常" in result:
                    useless_streak += 1
                else:
                    useless_streak = 0  # 有效信息,重置

                if name == "search_knowledge_base":
                    if "建议停止" in result: streak = 99
                    elif "未找到" in result: streak += 1
                    else: streak = 0
                yield json.dumps({"type": "tool_result", "data": result[:300]}, ensure_ascii=False)

                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                tool_results_summary.append(f"{name}: {result[:100]}")

            # === Analyzer 节点 ===
            # 工具执行完后, 如果内容不完整+未超限制, 让 LLM 确认"够不够"
            if calls < max_calls and analyzer_rounds < 2 and streak < 99:
                analyzer_rounds += 1
                analyzer_prompt = (
                    "你有以下工具执行结果:\n" +
                    "\n".join(tool_results_summary) +
                    "\n\n请判断: 信息是否足够给出完整回答?"
                    "如果够了, 直接写出最终答案。"
                    "如果不够, 明确说还需要什么信息, 系统会继续搜索。"
                )
                msgs.append({"role": "user", "content": analyzer_prompt})
                continue  # 回到循环顶部, 让 LLM 判断
            # ====================
        else:
            full_answer = content
            break

    if not full_answer:
        full_answer = ("[已达工具调用上限] 基于已收集数据,"
                       "请整理以上结果并给出最终分析。如果数据不足以回答,"
                       "明确说明缺失什么信息。")

    msgs.append({"role": "assistant", "content": full_answer})
    # 会话状态持久化: 只追加本轮新增消息, 并显式指定 as_node 避免
    # "Ambiguous update" (messages 被多个节点输出时 LangGraph 无法自动推断归属)
    new_msgs = msgs[start_len:]
    try:
        await agent_graph.aupdate_state(config, {"messages": new_msgs}, as_node="call_llm")
    except Exception:
        pass  # 状态保存失败不影响回答返回 (历史丢失好过整条 SSE 崩溃)

    yield json.dumps({"type": "done", "answer": full_answer,
                      "conversation_id": cid}, ensure_ascii=False)


# ═══════════════════════════════════════════════
# 结构化 Planner — JSON Task → Executor → Analyzer 闭环
# ═══════════════════════════════════════════════

from pydantic import BaseModel as PydanticBase

class StructuredTask(PydanticBase):
    id: int
    description: str
    tool: str
    args: dict = {}
    status: str = "pending"

class PlannerOutput(PydanticBase):
    tasks: list[StructuredTask]


async def _gen_structured_tasks(user_message: str, department: str) -> list[StructuredTask]:
    """LLM 生成结构化 JSON 任务列表"""
    tools_desc = "\n".join(
        f"- {t['function']['name']}: {t['function']['description'][:100]}"
        for t in TOOLS
    )
    prompt = f"""可用工具:
{tools_desc}

用户问题: {user_message}
部门: {department}

请输出一个 JSON 数组, 每个元素是一个任务对象:
[
  {{"id": 1, "description": "任务描述", "tool": "工具名", "args": {{"参数名": "参数值"}}}},
  ...
]

args 中必须包含该工具的所有 required 参数。输出纯 JSON, 不要其他内容:"""

    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    # 提取 JSON
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        raw = json.loads(text)
        tasks = [StructuredTask(**t) for t in raw]
        return tasks
    except (json.JSONDecodeError, Exception):
        # 降级: 返回纯文本步骤, 全部用 search_knowledge_base
        return [StructuredTask(id=1, description=user_message,
                               tool="search_knowledge_base",
                               args={"query": user_message, "department": department})]


async def run_structured_planner_stream(user_message: str, department: str = "HR",
                                        conversation_id: str = ""):
    """结构化 Planner: 生成 Task → 执行 → Analyzer 判断 → 不够继续 → 够了输出"""
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]

    # Phase 1: 生成结构化任务
    tasks = await _gen_structured_tasks(user_message, department)
    plan_text = [t.description for t in tasks]
    yield json.dumps({"type": "plan", "data": plan_text}, ensure_ascii=False)

    # Phase 2: 执行任务
    executed_results: list[str] = []
    all_done: set[str] = set()  # 去重
    calls, streak = 0, 0
    max_calls = 15
    max_analyzer_rounds = 2
    analyzer_count = 0
    full_answer = ""

    while True:
        # 执行 pending 任务
        pending = [t for t in tasks if t.status == "pending"]
        if not pending:
            break

        for task in pending:
            calls += 1
            if calls > max_calls: break

            # 去重
            call_key = f"{task.tool}:{json.dumps(task.args, sort_keys=True)}"
            if call_key in all_done:
                task.status = "skipped"
                continue
            all_done.add(call_key)

            yield json.dumps({"type": "tool_start", "tool": task.tool,
                              "args": task.args}, ensure_ascii=False)

            result = exec_tool(task.tool, task.args, department, streak)
            if task.tool == "search_knowledge_base":
                if "建议停止" in result: streak = 99
                elif "未找到" in result: streak += 1
                else: streak = 0

            yield json.dumps({"type": "tool_result", "tool": task.tool,
                              "data": result[:300]}, ensure_ascii=False)
            task.status = "completed"
            executed_results.append(f"[{task.tool}] {task.description}: {result[:200]}")

        if calls >= max_calls:
            break

        # Phase 3: Analyzer — LLM 判断信息是否充分
        if analyzer_count >= max_analyzer_rounds:
            break

        analyzer_count += 1
        analyzer_prompt = f"""已执行的任务结果:
{chr(10).join(executed_results[-10:])}

你是一个分析专家。请判断: 以上信息是否足够回答用户问题"{user_message}"?

如果足够, 直接输出最终答案。
如果不够, 输出一个 JSON 数组, 列出还需要执行的补充任务:
[{{"id": {len(tasks)+1}, "description": "...", "tool": "...", "args": {{...}}}}]

只输出 JSON 数组或最终答案, 二选一:"""

        analyzer_resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": analyzer_prompt}],
            temperature=0,
        )
        analyzer_text = analyzer_resp.choices[0].message.content.strip()

        # 尝试解析为 JSON (补充任务) 或直接作为答案
        try:
            clean = analyzer_text
            if "```" in clean:
                clean = clean.split("```")[1]
                if clean.startswith("json"): clean = clean[4:]
            extra = json.loads(clean)
            if isinstance(extra, list) and len(extra) > 0 and isinstance(extra[0], dict):
                new_tasks = []
                for t in extra:
                    try:
                        new_tasks.append(StructuredTask(**t))
                    except Exception:
                        pass
                if new_tasks:
                    tasks.extend(new_tasks)
                    yield json.dumps({"type": "status",
                                      "data": f"Analyzer: 信息不足, 新增 {len(new_tasks)} 个任务"},
                                     ensure_ascii=False)
                    continue  # 继续执行新任务
        except (json.JSONDecodeError, Exception):
            pass

        # 不是 JSON → 最终答案
        full_answer = analyzer_text
        break

    if not full_answer:
        # 没有明确答案 → 汇总执行结果作为答案
        full_answer = "## 排查结果汇总\n\n" + "\n\n".join(executed_results)

    # 用最终结果生成完整报告 (流式逐 token)
    final_prompt = f"根据以下排查结果, 对用户问题'{user_message}'生成一份完整的分析报告:\n\n" + "\n".join(executed_results)
    final_stream = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": final_prompt}],
        temperature=0,
        stream=True,
    )
    final_answer = ""
    async for chunk in final_stream:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            final_answer += token
            yield json.dumps({"type": "token", "data": token}, ensure_ascii=False)

    yield json.dumps({"type": "done", "answer": final_answer,
                      "conversation_id": cid, "plan": plan_text}, ensure_ascii=False)


# ── Planner (阻塞) ──

async def run_agent_with_plan(user_message: str, department: str = "HR",
                              conversation_id: str = "") -> dict:
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]
    config = {"configurable": {"thread_id": cid}}

    plan = await _gen_plan(user_message, department)
    plan_text = chr(10).join(f"{i+1}. {s}" for i, s in enumerate(plan))
    initial = _build_initial(department, user_message, f"执行计划:\n{plan_text}")

    final = await agent_graph.ainvoke(initial, config)
    return {"answer": final.get("final_answer", ""), "plan": plan,
            "conversation_id": cid, "total_calls": final.get("total_calls", 0)}


# ── Planner (流式) ──

async def run_agent_with_plan_stream(user_message: str, department: str = "HR",
                                     conversation_id: str = ""):
    cid = conversation_id or hashlib.md5(user_message.encode()).hexdigest()[:12]
    config = {"configurable": {"thread_id": cid}}

    plan = await _gen_plan(user_message, department)
    yield json.dumps({"type": "plan", "data": plan}, ensure_ascii=False)

    plan_text = chr(10).join(f"{i+1}. {s}" for i, s in enumerate(plan))
    initial = _build_initial(department, user_message, f"执行计划:\n{plan_text}")

    async for event in agent_graph.astream(initial, config, stream_mode="values"):
        if event.get("final_answer"):
            yield json.dumps({"type": "done", "answer": event["final_answer"],
                              "conversation_id": cid, "plan": plan}, ensure_ascii=False)
            return

    yield json.dumps({"type": "done", "answer": "",
                      "conversation_id": cid, "plan": plan}, ensure_ascii=False)
