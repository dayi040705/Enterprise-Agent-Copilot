"""
Agent 评测体系 v2 — 多维度量化评估

指标:
  1. Tool Success Rate    — 工具调用成功率
  2. LLM Judge            — 答案质量 (忠实度+相关性)
  3. Token 统计           — Input / Output tokens
  4. Latency 统计         — TTF / Total / Avg per tool
  5. Cost 统计            — 基于 DeepSeek 定价估算
"""
import json, time
from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from services.agent import agent_chat_stream
from services.multi_agent import _route_intent

judge_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# DeepSeek V4 定价 (每百万 token)
PRICE_INPUT = 0.28   # $0.28 / 1M input tokens
PRICE_OUTPUT = 1.10  # $1.10 / 1M output tokens

TEST_CASES = [
    # ===== RAG: 纯知识库检索 =====
    {"question": "请假流程是什么？需要谁审批？",
     "department": "HR", "tags": ["RAG"], "expected_tools": ["search_knowledge_base"]},
    {"question": "公司 VPN 怎么配置？密码有什么要求？",
     "department": "TECH", "tags": ["RAG"], "expected_tools": ["search_knowledge_base"]},
    {"question": "病假和事假的工资怎么算？有什么区别？",
     "department": "HR", "tags": ["RAG"], "expected_tools": ["search_knowledge_base"]},

    # ===== Agent: 工具调用 =====
    {"question": "user-service 日志里有什么错误？",
     "department": "TECH", "tags": ["Agent"], "expected_tools": ["search_logs"]},
    {"question": "payment-service 今天有没有支付失败的记录？",
     "department": "TECH", "tags": ["Agent"], "expected_tools": ["search_logs"]},
    {"question": "order-service 为什么变慢了？看看日志",
     "department": "TECH", "tags": ["Agent"], "expected_tools": ["search_logs"]},

    # ===== Planner: 多步复杂任务 =====
    {"question": "payment-service Redis 超时了, 查日志+工单+历史经验, 出完整故障报告",
     "department": "TECH", "tags": ["Planner"],
     "expected_tools": ["search_logs", "query_database", "search_memory"]},
    {"question": "user-service 接口500错误, 全面排查日志、数据库连接、历史事故, 出根因分析",
     "department": "TECH", "tags": ["Planner"],
     "expected_tools": ["search_logs", "search_memory", "search_knowledge_base"]},

    # ===== Memory: 长期记忆检索 =====
    {"question": "之前数据库连接池耗尽那次是怎么解决的？",
     "department": "TECH", "tags": ["Memory"], "expected_tools": ["search_memory"]},
    {"question": "以前 Redis 连接超时有过什么处理方案？",
     "department": "TECH", "tags": ["Memory"], "expected_tools": ["search_memory"]},

    # ===== Database: 业务数据查询 =====
    {"question": "张三在 HR 部门的请假记录有哪些？",
     "department": "HR", "tags": ["Database"], "expected_tools": ["query_database"]},
    {"question": "最近有哪些待处理的 IT 工单？谁在处理？",
     "department": "TECH", "tags": ["Database"], "expected_tools": ["query_database"]},
    {"question": "TECH 部门有哪些在职员工？",
     "department": "TECH", "tags": ["Database"], "expected_tools": ["query_database"]},

    # ===== 混合: 多工具协作 =====
    {"question": "给我查一下payment-service今天有没有Redis超时的错误日志，再帮我看看有没有相关的未解决工单",
     "department": "TECH", "tags": ["混合"], "expected_tools": ["search_logs", "query_database"]},
]


async def _judge_answer(question: str, answer: str) -> dict:
    """LLM Judge: 评判 Agent 回答质量"""
    prompt = f"""你是一个评测裁判。请对以下 Agent 回答打分。

用户问题: {question}
Agent 回答: {answer[:2000]}

## 评分规则 (重要):

faithfulness 评判标准:
- 1.0: 每条声明都引用了工具返回的数据(日志行/数据库记录/文档片段)
- 0.7-0.9: 大部分基于证据, 部分合理的推测但标注了"可能"/"推测"
- 0.4-0.6: 证据和支持各半, 有一些未经证实的声明
- 0.1-0.3: 大部分是通用建议或推测, 缺乏直接证据支持
- 0.0: 完全编造, 与工具返回数据矛盾

注意:
- 报告中正常出现"建议"和"可能原因"不应给0分
- 只要 Agent 确实调了工具并引用了结果, 基线分不低于 0.3
- 报告不引用任何工具数据才给 0 分

relevancy 评判标准:
- 1.0: 直接回答了用户问的每个子问题, 没有跑题也没有遗漏
- 0.7-0.9: 基本回答了问题, 但附带了一些无关信息(如用户问请假流程却顺便介绍了报销)
- 0.4-0.6: 部分相关, 但答了很多用户没问的内容, 或遗漏了关键部分
- 0.1-0.3: 只有少量内容切题, 大部分答非所问
- 0.0: 完全跑题, 和用户问题无关

请输出 JSON:
{{"faithfulness": 0.0-1.0, "relevancy": 0.0-1.0, "explanation": "一句话"}}
只输出 JSON:"""
    resp = await judge_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = resp.choices[0].message.content.strip()
    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
            text = text.split("```")[0]
        # 提取第一个 JSON 对象
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        return json.loads(text)
    except (json.JSONDecodeError, Exception):
        return {"faithfulness": 0.5, "relevancy": 0.5, "explanation": f"parse error: {text[:50]}"}


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数: 中文 ~1.5 char/token, 英文 ~4 char/token"""
    return max(1, int(len(text) / 2))


async def run_agent_eval() -> dict:
    """多维度 Agent 评测"""
    cases = []
    total_calls = total_errors = total_input_tokens = total_output_tokens = 0
    total_ttf = 0.0  # Time To First token
    total_latency = 0.0
    faith_scores = []; relev_scores = []
    router_correct = 0; router_total = 0

    for i, case in enumerate(TEST_CASES):
        print(f"[{i+1}/{len(TEST_CASES)}] {case['question'][:50]}...")

        # Router 评测 (不阻塞主流程)
        try:
            route, agent = await _route_intent(case["question"])
            expected_route = "complex" if case.get("tags") and "Planner" in case["tags"] else "simple"
            if route == expected_route:
                router_correct += 1
            router_total += 1
        except Exception:
            pass

        called = set(); errors = 0; calls = 0
        tokens_in = 0; tokens_out = 0; answer = ""
        ttf = 0.0; case_start = time.time(); first_token = True

        # 估算 input tokens
        sys_prompt = f"你是企业 Agent。部门: {case['department']}。"
        user_msg = case["question"]
        tokens_in = _estimate_tokens(sys_prompt) + _estimate_tokens(user_msg)

        async for event_json in agent_chat_stream(
            case["question"], case["department"], f"eval_v2_{i}"
        ):
            ev = json.loads(event_json)

            if ev["type"] in ("tool_call", "tool_start"):
                called.add(ev.get("tool", "")); calls += 1
                # 估算工具参数 token
                args_str = json.dumps(ev.get("args", {}), ensure_ascii=False)
                tokens_in += _estimate_tokens(args_str)

            elif ev["type"] == "tool_result":
                data = ev.get("data", "")
                if "工具执行异常" in data or "[错误]" in data: errors += 1
                tokens_in += _estimate_tokens(data)

            elif ev["type"] == "token":
                if first_token:
                    ttf = round(time.time() - case_start, 2)
                    first_token = False
                tokens_out += 1  # 每个 token 事件 ≈ 1 个 token

            elif ev["type"] == "done":
                answer = ev.get("answer", "")

        elapsed = round(time.time() - case_start, 1)
        total_calls += calls; total_errors += errors
        total_input_tokens += tokens_in; total_output_tokens += tokens_out
        total_ttf += ttf; total_latency += elapsed

        # LLM Judge
        judge = {}
        if len(answer) > 30:
            try:
                judge = await _judge_answer(case["question"], answer)
                faith_scores.append(judge.get("faithfulness", 0))
                relev_scores.append(judge.get("relevancy", 0))
            except Exception:
                pass

        expected = set(case["expected_tools"])
        coverage = len(expected & called) / len(expected) if expected else 1.0

        cases.append({
            "question": case["question"][:50],
            "tags": ", ".join(case.get("tags", [])),
            "calls": calls, "errors": errors, "coverage": round(coverage, 2),
            "ttf": ttf, "total_time": elapsed,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "faithfulness": judge.get("faithfulness", 0),
            "relevancy": judge.get("relevancy", 0),
        })

    n = len(TEST_CASES)
    total_tokens = total_input_tokens + total_output_tokens
    # Cost: 按百万 token 计价
    cost_input = (total_input_tokens / 1_000_000) * PRICE_INPUT
    cost_output = (total_output_tokens / 1_000_000) * PRICE_OUTPUT
    total_cost = cost_input + cost_output

    return {
        "cases": n,
        "router": {
            "accuracy": round(router_correct / router_total, 4) if router_total else 0,
            "correct": router_correct,
            "total": router_total,
        },
        "tool": {
            "success_rate": round(1 - total_errors / total_calls, 4) if total_calls else 0,
            "avg_calls": round(total_calls / n, 1),
            "total_errors": total_errors,
        },
        "judge": {
            "avg_faithfulness": round(sum(faith_scores) / len(faith_scores), 4) if faith_scores else 0,
            "avg_relevancy": round(sum(relev_scores) / len(relev_scores), 4) if relev_scores else 0,
        },
        "latency": {
            "avg_ttf_sec": round(total_ttf / n, 2),      # 首 token 延迟
            "avg_total_sec": round(total_latency / n, 1),  # 总耗时
        },
        "tokens": {
            "total_input": total_input_tokens,
            "total_output": total_output_tokens,
            "avg_input_per_case": round(total_input_tokens / n),
            "avg_output_per_case": round(total_output_tokens / n),
        },
        "cost": {
            "total_usd": round(total_cost, 6),
            "avg_per_case_usd": round(total_cost / n, 6),
            "input_cost": round(cost_input, 6),
            "output_cost": round(cost_output, 6),
        },
        "details": cases,
    }


def print_eval_report(r: dict):
    print("\n" + "=" * 60)
    print("  Agent 评测报告 v2")
    print("=" * 60)
    print(f"  Cases: {r['cases']}")
    if "router" in r:
        print(f"  Router Accuracy:     {r['router']['accuracy']:.1%} ({r['router']['correct']}/{r['router']['total']})")
    print()
    print(f"  Tool Success Rate:   {r['tool']['success_rate']:.1%}")
    print(f"  Avg Calls / Case:    {r['tool']['avg_calls']}")
    print(f"  Faithfulness:        {r['judge']['avg_faithfulness']:.1%}")
    print(f"  Relevancy:           {r['judge']['avg_relevancy']:.1%}")
    print()
    print(f"  Avg TTF:             {r['latency']['avg_ttf_sec']}s")
    print(f"  Avg Total Time:      {r['latency']['avg_total_sec']}s")
    print()
    print(f"  Tokens In:           {r['tokens']['total_input']}")
    print(f"  Tokens Out:          {r['tokens']['total_output']}")
    print()
    print(f"  Estimated Cost:      ${r['cost']['total_usd']:.4f}")
    print(f"  Cost / Case:         ${r['cost']['avg_per_case_usd']:.4f}")
    print("=" * 60)
    # 按标签分组展示
    tag_groups = {}
    for d in r["details"]:
        tag = d.get("tags", "其他")
        if tag not in tag_groups: tag_groups[tag] = []
        tag_groups[tag].append(d)

    for tag, items in tag_groups.items():
        avg_f = sum(it.get("faithfulness", 0) for it in items) / len(items) if items else 0
        avg_c = sum(it["calls"] for it in items) / len(items) if items else 0
        print(f"\n  [{tag}] ({len(items)} 题, avg {avg_c:.1f} calls, faith {avg_f:.0%})")
        for d in items:
            f = d.get('faithfulness', 0)
            r = d.get('relevancy', 0)
            icon = "OK" if f > 0.6 else ("WARN" if f > 0 else "FAIL")
            print(f"    [{icon}] {d['question'][:45]} | {d['calls']} calls | TTF {d['ttf']}s | faith {f:.0%} relev {r:.0%}")
