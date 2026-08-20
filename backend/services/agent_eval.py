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
from services.multi_agent import multi_agent_chat
from services.multi_agent import _route_intent

judge_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com",
                           timeout=120, max_retries=2)

# DeepSeek V4 定价 (每百万 token)
PRICE_INPUT = 0.28   # $0.28 / 1M input tokens
PRICE_OUTPUT = 1.10  # $1.10 / 1M output tokens

TEST_CASES = [
    # ===== 数据查询 — OLTP 实时数据 =====
    {"question": "帮我查一下最近 10 个已取消的订单, 看看他们的订单状态和时间",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_mysql"]},
    {"question": "查询评分最高的前 5 个 Listing, 列出它们的品类和评价数",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_mysql"]},
    {"question": "过去 30 天销量最高的 5 个 SKU 分别卖了多少？",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_analytics"]},

    # ===== 数据查询 — OLAP 趋势分析 =====
    {"question": "退款率最高的 3 个 SKU 是什么？各退了多少单？退款率分别是多少？",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_analytics"]},
    {"question": "最近 30 天销量趋势怎么样？每天卖了多少、收入多少？",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_analytics"]},
    {"question": "平均评分最低的 5 个 Listing 是哪些？它们的评价数和品类是什么？",
     "department": "TECH", "tags": ["数据查询"], "expected_tools": ["query_mysql"]},

    # ===== 知识库检索 — 电商 SOP =====
    {"question": "买家收到破损商品要求退货, 我应该怎么处理？流程是什么？",
     "department": "TECH", "tags": ["知识检索"], "expected_tools": ["search_knowledge_base"]},
    {"question": "跟卖是什么？如果有人跟卖我的 Listing, 我该怎么应对？",
     "department": "TECH", "tags": ["知识检索"], "expected_tools": ["search_knowledge_base"]},
    {"question": "新品上架后怎么投放广告？广告预算和 ACOS 怎么控制？",
     "department": "TECH", "tags": ["知识检索"], "expected_tools": ["search_knowledge_base"]},
    {"question": "库存低于安全库存线了, 补货的流程和需要注意什么？",
     "department": "TECH", "tags": ["知识检索"], "expected_tools": ["search_knowledge_base"]},

    # ===== 异常诊断 — 单维度排查 =====
    {"question": "SKU 51a41e5b 的评分是多少？有什么评价？",
     "department": "TECH", "tags": ["异常诊断"], "expected_tools": ["query_mysql"]},
    {"question": "今天 SP-API 数据同步的录入率是多少？有没有失败的批次？失败原因是什么？",
     "department": "TECH", "tags": ["异常诊断"], "expected_tools": ["query_mysql"]},
    {"question": "SKU 51a41e5b 的价格和评分是多少？",
     "department": "TECH", "tags": ["异常诊断"], "expected_tools": ["query_listing"]},

    # ===== 复杂排障 — 多源交叉诊断 =====
    {"question": "Listing 51a41e5b 转化率从 8% 跌到 2% 了, 全面排查: 查评分变化、查退款率趋势、查跟卖应对 SOP、查广告投放策略, 输出诊断报告",
     "department": "TECH", "tags": ["复杂排障"],
     "expected_tools": ["query_mysql", "query_analytics", "search_knowledge_base"]},
    {"question": "过去 7 天退款率突然从 2% 飙升到 8%, 全面排查: 查退款率高的 SKU、查差评内容、查售后处理 SOP、查历史类似事故经验",
     "department": "TECH", "tags": ["复杂排障"],
     "expected_tools": ["query_analytics", "query_mysql", "search_knowledge_base", "search_memory"]},

    # ===== 长期记忆 — 历史经验 =====
    {"question": "上次 Listing 被恶意差评那次是怎么处理的？最后恢复了吗？",
     "department": "TECH", "tags": ["记忆检索"], "expected_tools": ["search_memory"]},
    {"question": "之前 PrimeDay 备货不足那次是怎么处理的？后来吸取了什么教训？",
     "department": "TECH", "tags": ["记忆检索"], "expected_tools": ["search_memory"]},

    # ===== 数据管道 — sync_logs 监控 =====
    {"question": "查一下最近 24 小时 SP-API 数据同步的健康度, 录入率是多少？哪个表的同步有异常？",
     "department": "TECH", "tags": ["数据管道"], "expected_tools": ["query_mysql"]},

    # ===== 混合 — 多工具协作 =====
    {"question": "给我查一下退款率最高的 SKU 是什么, 然后看看对应的 Listing 评分变化, 再查一下售后处理应该怎么做",
     "department": "TECH", "tags": ["混合"],
     "expected_tools": ["query_analytics", "query_mysql", "search_knowledge_base"]},
    {"question": "查一下最近有没有库存预警的 SKU, 然后告诉我库存管理规范里补货的流程是什么",
     "department": "TECH", "tags": ["混合"],
     "expected_tools": ["query_analytics", "search_knowledge_base"]},
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
- 只要Agent确实调了工具且回答切题,基线分不低于0.4——即使没显式标注来源
- 完全没调工具就回答=0分
- 调了工具但答案和工具返回的数据矛盾=0分
- 建议和推测不扣分
- relevancy切题就高,不用太严

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
    total_ttf = 0.0
    total_latency = 0.0
    faith_scores = []; relev_scores = []
    router_correct = 0; router_total = 0

    for i, case in enumerate(TEST_CASES):
        print(f"[{i+1}/{len(TEST_CASES)}] {case['question'][:50]}...")

        # Router 评测 (不阻塞主流程)
        try:
            route, agent = await _route_intent(case["question"])
            expected_route = "complex" if case.get("tags") and "复杂排障" in case["tags"] else "simple"
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

        # 复杂排障 → Multi-Agent, 其余 → 单 Agent
        is_complex = case.get("tags") and "复杂排障" in case["tags"]
        stream_source = multi_agent_chat(case["question"], case["department"]) if is_complex else \
                        agent_chat_stream(case["question"], case["department"], f"eval_v2_{i}")
        async for event_json in stream_source:
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
