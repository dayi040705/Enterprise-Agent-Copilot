from services.retriever import vector_search
from services.bm25 import bm25_search
from services.reranker import rerank


def rrf_fusion(
        vector_results,
        bm25_results,
        k=60
):
    """RRF (Reciprocal Rank Fusion) 融合多路召回"""

    scores = {}
    docs = {}

    # 向量检索排名
    for rank, item in enumerate(vector_results):
        key = item["text"]
        docs[key] = item
        scores[key] = scores.get(key, 0) + (
            1 / (k + rank + 1)
        )

    # BM25 检索排名
    for rank, item in enumerate(bm25_results):
        key = item["text"]
        docs[key] = item
        scores[key] = scores.get(key, 0) + (
            1 / (k + rank + 1)
        )

    results = []
    for key, score in scores.items():
        results.append({
            "text": docs[key]["text"],
            "metadata": docs[key]["metadata"],
            "score": score
        })

    # RRF 分数降序
    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results


def hybrid_search(
        question,
        department,
        top_k=5
):
    """混合检索: 向量 + BM25 → RRF 融合 → Reranker 精排"""

    # 1. 多路召回
    vector_results = vector_search(
        question,
        department,
        top_k=20
    )

    bm25_results = bm25_search(
        question,
        department,
        top_k=20
    )

    # 2. RRF 融合
    fused = rrf_fusion(
        vector_results,
        bm25_results
    )

    # 3. Reranker 精排
    return rerank(
        question,
        fused,
        top_k=top_k,
        score_threshold=-2
    )
