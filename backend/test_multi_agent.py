"""测试 Multi-Agent 协作"""
import asyncio, json, sys
sys.stdout.reconfigure(encoding='utf-8')
from services.multi_agent import multi_agent_chat


async def main():
    async for event_json in multi_agent_chat(
        "payment-service Redis 超时了, 帮我在日志+知识库+工单+历史经验里全面排查, 出分析报告",
        department="TECH"
    ):
        ev = json.loads(event_json)
        if ev["type"] == "plan":
            print(f"Plan: {len(ev['data'])} tasks")
            for t in ev["data"]: print(f"  - {t[:60]}")
        elif ev["type"] == "status":
            print(f"  [{ev['data'][:80]}]")
        elif ev["type"] == "done":
            rv = ev.get("review", {})
            print(f"\nReviewer: faith={rv.get('faithfulness',0):.0%}, "
                  f"relev={rv.get('relevancy',0):.0%}, passed={rv.get('passed')}")
            print(f"Answer: {len(ev['answer'])} chars")


if __name__ == "__main__":
    asyncio.run(main())
