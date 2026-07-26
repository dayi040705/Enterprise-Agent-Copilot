"""RAG LLM Judge 评测 — DeepSeek 自动打分"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from services.evaluation import (
    run_llm_judge_evaluation,
    print_judge_report,
    save_judge_report,
)


async def main():
    scores = await run_llm_judge_evaluation()
    print_judge_report(scores)
    save_judge_report(scores)


if __name__ == "__main__":
    asyncio.run(main())
