"""
诊断：员工请假流程 — 逐段排查
"""
from services.chroma import collection
from services.embedding import embedding_texts
from services.reranker import reranker

question = "员工请假流程"
department = "HR"
vector = embedding_texts([question])[0]

print("=" * 60)
print("【1】collection.query — $and 过滤")
print("=" * 60)
r = collection.query(
    query_embeddings=[vector],
    n_results=10,
    where={
        "$and": [
            {"department": department},
            {"status": "active"}
        ]
    }
)
docs = r["documents"][0]
metas = r["metadatas"][0]
print(f"返回 {len(docs)} 条")
for i, (meta, doc) in enumerate(zip(metas, docs)):
    print(f"  [{i}] {meta.get('filename')} | page={meta.get('page')} | {doc[:50]}...")

if not docs:
    print("⚠️ 向量检索就返回空了！ChromaDB 里没有匹配的文档")
    exit()

print("\n" + "=" * 60)
print("【2】Reranker 打分")
print("=" * 60)
pairs = [[question, doc] for doc in docs]
scores = reranker.compute_score(pairs)
print(f"分数: {[f'{s:.4f}' for s in scores]}")
print(f"最高: {max(scores):.4f}, 最低: {min(scores):.4f}")
for threshold in [2, 0, -2, -5]:
    passed = sum(1 for s in scores if s >= threshold)
    print(f"  threshold={threshold:2d} → 通过 {passed}/{len(scores)} 条")

print("\n" + "=" * 60)
print("【3】完整 retrieve_context")
print("=" * 60)
from services.retriever import retrieve_context
result = retrieve_context(question, department=department, top_k=20)
print(f"返回 {len(result)} 条")
for i, r in enumerate(result):
    print(f"  [{i}] score={r['score']:.4f} | {r['text'][:60]}")
