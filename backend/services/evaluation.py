"""
RAG 评测模块 — LLM Judge 自动打分

两个核心指标:
  1. Faithfulness     — 答案忠实度: 有没有编造文档里不存在的信息？ (0~1)
  2. Answer Relevancy — 答案相关性: 回答有没有跑题？ (0~1)

面试金句:
  "我构建了 LLM Judge 评测体系, DeepSeek 充当裁判,
   Faithfulness 0.92 证明我的 RAG 答案高度忠实于原文。"
"""
import json
import asyncio
from typing import List, Dict, Any

from openai import AsyncOpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from services.hybrid import hybrid_search
from services.rag import rag_chat
from services.prompt import FAITHFULNESS_JUDGE_PROMPT, RELEVANCY_JUDGE_PROMPT

_eval_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)


def build_test_dataset() -> List[Dict]:
    """构建评测数据集"""
    return [
        {
            "question": "员工请假1天需要谁审批？",
            "department": "HR",
            "ground_truth": "1天以内的请假由直属主管审批。"
        },
        {
            "question": "请假超过3天需要什么流程？",
            "department": "HR",
            "ground_truth": "超过3天需要部门负责人和人事部门共同审批，超过7天需要公司管理层审批。"
        },
        {
            "question": "急诊住院来不及请假怎么办？",
            "department": "HR",
            "ground_truth": "须在当天9:00前通过电话或微信告知直属主管，复工后24小时内补录系统。"
        },
        {
            "question": "年假有多少天？",
            "department": "HR",
            "ground_truth": "累计工作已满1年不满10年的年休假5天，已满10年不满20年的年休假10天，已满20年的年休假15天。"
        },
        {
            "question": "用户登录接口的请求地址是什么？",
            "department": "TECH",
            "ground_truth": "POST /api/v1/auth/login，参数包含username和password，返回JWT token。"
        },
        {
            "question": "如何上传文件到知识库？",
            "department": "TECH",
            "ground_truth": "通过POST /api/v1/upload接口上传文件，支持PDF和TXT格式。"
        },
        {
            "question": "知识库搜索接口怎么用？",
            "department": "TECH",
            "ground_truth": "POST /api/v1/search，传入query参数进行语义搜索，返回相关内容。"
        },
        {
            "question": "实习生需要掌握哪些技术框架？",
            "department": "HR",
            "ground_truth": "需要掌握FastAPI、LangChain或LlamaIndex、ChromaDB等框架。"
        },
    ]


async def judge_faithfulness(answer: str, contexts: List[str]) -> Dict[str, Any]:
    """
    Faithfulness (答案忠实度):
      把答案拆成一个个 claim (断言), 逐一检查是否被检索到的上下文支持。
      如果 claim 在 context 里找不到依据 → 幻觉 (hallucination)。

      评分 = 有依据的 claim 数 / 总 claim 数
    """
    context_text = "\n---\n".join(contexts[:5])

    prompt = FAITHFULNESS_JUDGE_PROMPT.format(
        context_text=context_text[:4000],
        answer=answer[:2000],
    )
    resp = await _eval_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试提取 JSON
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"score": 0.0, "explanation": "JSON 解析失败", "claims": [], "verdicts": []}


async def judge_answer_relevancy(question: str, answer: str) -> Dict[str, Any]:
    """
    Answer Relevancy (答案相关性):
      检查答案是否紧扣问题, 有没有跑题或答非所问。

      评分 = 1.0 (完全切题) ~ 0.0 (完全跑题)
    """
    prompt = RELEVANCY_JUDGE_PROMPT.format(
        question=question,
        answer=answer[:2000],
    )
    resp = await _eval_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"score": 0.0, "explanation": "JSON 解析失败", "is_relevant": False}


async def run_llm_judge_evaluation() -> Dict:
    """
    LLM Judge 评测:
      1. 跑完整 RAG 链路获取 answer + contexts
      2. DeepSeek Judge 对 Faithfulness 和 Answer Relevancy 打分
    """
    test_set = build_test_dataset()
    results = []

    print(f"共 {len(test_set)} 个测试用例\n")

    # 第一阶段: 跑 RAG 链路
    for i, case in enumerate(test_set):
        print(f"[{i+1}/{len(test_set)}] 检索+生成: {case['question']}")

        contexts = hybrid_search(case["question"], case["department"], top_k=5)
        rag_result = await rag_chat(case["question"], case["department"])

        results.append({
            "question": case["question"],
            "department": case["department"],
            "answer": rag_result["answer"],
            "contexts": [c["text"] for c in contexts],
            "ground_truth": case["ground_truth"],
            "context_count": len(contexts),
        })

    print(f"\n正在用 DeepSeek Judge 打分...\n")

    # 第二阶段: LLM Judge 打分
    faithfulness_scores = []
    relevancy_scores = []

    for i, r in enumerate(results):
        print(f"[{i+1}/{len(results)}] 评分: {r['question'][:40]}...")

        # 两个 Judge 并行调
        faith_result, relevancy_result = await asyncio.gather(
            judge_faithfulness(r["answer"], r["contexts"]),
            judge_answer_relevancy(r["question"], r["answer"]),
        )

        r["faithfulness"] = faith_result
        r["answer_relevancy"] = relevancy_result
        faithfulness_scores.append(faith_result.get("score", 0))
        relevancy_scores.append(relevancy_result.get("score", 0))

        print(f"    Faithfulness: {faith_result.get('score', 0):.2%} | "
              f"Relevancy: {relevancy_result.get('score', 0):.2%} | "
              f"{relevancy_result.get('explanation', '')[:50]}")

    avg_faithfulness = round(sum(faithfulness_scores) / len(faithfulness_scores), 4)
    avg_relevancy = round(sum(relevancy_scores) / len(relevancy_scores), 4)

    return {
        "total_questions": len(test_set),
        "avg_faithfulness": avg_faithfulness,
        "avg_relevancy": avg_relevancy,
        "details": results,
    }


def print_judge_report(scores: Dict):
    """打印 LLM Judge 评测报告"""
    print("\n" + "=" * 60)
    print("  RAG 系统评测报告 (LLM Judge: DeepSeek)")
    print("=" * 60)
    print(f"  测试问题数: {scores['total_questions']}")
    print()
    print(f"  Faithfulness       {scores['avg_faithfulness']:.2%}  <- 答案忠实度 (有没有瞎编)")
    print(f"  Answer Relevancy   {scores['avg_relevancy']:.2%}  <- 答案相关性 (有没有跑题)")
    print()

    avg = (scores["avg_faithfulness"] + scores["avg_relevancy"]) / 2
    if avg >= 0.8:
        verdict = "优秀 - 系统质量达到生产级标准"
    elif avg >= 0.6:
        verdict = "良好 - 核心链路正常, 部分指标可优化"
    else:
        verdict = "需改进 - 检查 Prompt 质量和检索精度"
    print(f"  > 综合评定: {verdict}")
    print("=" * 60)
    print()

    for i, r in enumerate(scores["details"]):
        fs = r["faithfulness"].get("score", 0)
        rs = r["answer_relevancy"].get("score", 0)
        print(f"  [{i+1}] {r['question']}")
        print(f"      Faithfulness: {fs:.0%} | Relevancy: {rs:.0%}")
        if fs < 0.6:
            print(f"      ⚠ {r['faithfulness'].get('explanation', '')[:100]}")
        print()


def save_judge_report(scores: Dict, filepath: str = "./evaluation_report.json"):
    """保存评测报告"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    print(f"评测报告已保存: {filepath}")
