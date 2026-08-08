"""
Reranker — Cross-Encoder 精排

Bi-Encoder (粗排) vs Cross-Encoder (精排):
  Bi-Encoder:  问题和文档各自独立编码 → 算余弦 → 快但粗
  Cross-Encoder: 问题和文档拼在一起过完整 Transformer → 每对 token 做 Attention → 慢但准

当前模型: BAAI/bge-reranker-base (sentence-transformers 版, 兼容性好)
"""
from sentence_transformers import CrossEncoder

# 优先用本地缓存 (避免 HuggingFace 网络问题)
import os
model_name = "BAAI/bge-reranker-base"
local_path = os.path.expanduser("~/.cache/huggingface/hub/models--BAAI--bge-reranker-base/snapshots")
if os.path.exists(local_path):
    # 取最新版本的 snapshot
    versions = sorted(os.listdir(local_path), reverse=True)
    if versions:
        model_name = os.path.join(local_path, versions[0])
        print(f"[Reranker] 使用本地缓存: {model_name}")

reranker = CrossEncoder(model_name)


def rerank(question, documents, top_k=5, score_threshold=-2):
    """
    精排: 对粗排结果逐个打分, 过滤低分, 取 top_k
    参数:
      question:        用户问题
      documents:       [{"text": "...", "metadata": {...}}, ...]
      top_k:           返回条数
      score_threshold: 最低分阈值, -2 过滤噪音 (默认)
    """
    if not documents:
        return []

    pairs = [[question, doc["text"]] for doc in documents]
    scores = reranker.predict(pairs)

    for doc, score in zip(documents, scores):
        doc["score"] = float(score)

    results = [doc for doc in documents if doc["score"] >= score_threshold]
    results.sort(key=lambda x: x["score"], reverse=True)

    return results[:top_k]
