"""Agent 测试 — 覆盖所有模式和工具"""
import asyncio, json, sys
sys.stdout.reconfigure(encoding='utf-8')


async def main():
    from services.agent import agent_chat, agent_chat_with_plan

    # ==== 1. ReAct 模式 — 知识库 + 日志 ====
    print("=" * 60)
    print("[Test 1] ReAct + 日志分析")
    r = await agent_chat(
        "user-service 500错误, 查日志分析",
        "TECH",
        conversation_id="test_1",
        max_total_calls=4,
    )
    print(f"模式: {r.mode}, 工具调用: {r.total_calls} 次")
    for t in r.tasks:
        if t.tool_name:
            print(f"  [{t.tool_name}] {json.dumps(t.tool_args, ensure_ascii=False)[:80]}")
    print(f"答案: {r.answer[:200]}...\n")

    # ==== 2. ReAct + 参数校验 ====
    print("=" * 60)
    print("[Test 2] Pydantic 参数校验 — 搜不存在的服务")
    r = await agent_chat(
        "查 auth-service 错误日志",
        "TECH",
        conversation_id="test_2",
        max_total_calls=2,
    )
    print(f"工具调用: {r.total_calls} 次")
    for t in r.tasks:
        if t.tool_name:
            print(f"  [{t.tool_name}] {json.dumps(t.tool_args, ensure_ascii=False)[:80]}")
            if t.result_preview:
                print(f"    返回: {t.result_preview[:60]}")
    print(f"答案: {r.answer[:200]}...\n")

    # ==== 3. 长期记忆 — 第一次查询后自动存入 ====
    print("=" * 60)
    print("[Test 3] 长期记忆 — 搜历史经验")
    r = await agent_chat(
        "数据库连接池耗尽怎么处理",
        "TECH",
        conversation_id="test_3",
        max_total_calls=3,
    )
    for t in r.tasks:
        if t.tool_name:
            print(f"  [{t.tool_name}] {json.dumps(t.tool_args, ensure_ascii=False)[:80]}")
    print(f"答案: {r.answer[:150]}...\n")

    # ==== 4. Planner 模式 ====
    print("=" * 60)
    print("[Test 4] Planner — 先出计划再执行")
    r = await agent_chat_with_plan(
        "user-service 500错误, 全面排查并出分析报告",
        "TECH",
    )
    print(f"模式: {r.mode}")
    print(f"计划: {len(r.plan)} 步")
    for i, step in enumerate(r.plan):
        print(f"  {i+1}. {step}")
    print(f"工具调用: {r.total_calls} 次")
    print(f"答案: {len(r.answer)} 字\n")

    # ==== 5. 多轮对话记忆 ====
    print("=" * 60)
    print("[Test 5] 短期记忆 — 多轮对话")
    conv = "test_memory_2"
    r1 = await agent_chat("年假有多少天？", "HR", conversation_id=conv)
    print(f"第1轮: {r1.answer[:60]}...")
    r2 = await agent_chat("那病假呢？有什么区别？", "HR", conversation_id=conv)
    print(f"第2轮: {r2.answer[:80]}...")

    # ==== 6. AgentResult 序列化 ====
    print("\n" + "=" * 60)
    print("[Test 6] AgentResult 可序列化")
    j = r.model_dump_json(indent=2, ensure_ascii=False)
    print(f"JSON: {len(j)} 字节")
    print(f"字段: answer, mode, conversation_id, tasks, turns, total_calls")


if __name__ == "__main__":
    asyncio.run(main())
