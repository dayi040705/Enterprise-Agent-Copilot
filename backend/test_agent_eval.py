"""Agent 评测 v2"""
import asyncio, sys
sys.stdout.reconfigure(encoding='utf-8')
from services.agent_eval import run_agent_eval, print_eval_report

async def main():
    r = await run_agent_eval()
    print_eval_report(r)

if __name__ == "__main__":
    asyncio.run(main())
