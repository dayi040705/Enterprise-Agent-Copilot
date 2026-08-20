from services.chroma import collection
from services.embedding import embedding_texts


def vector_search(
        question,
        department,
        top_k=20
):
    """纯向量语义检索"""

    # 1. 问题向量化
    vector = embedding_texts(
        [question]
    )[0]

    # 2. 向量检索 + 部门/状态过滤 (ADMIN 不受部门限制)
    if department == "ADMIN":
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where={"status": "active"}
        )
    else:
        result = collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where={
                "$and": [
                    {"department": department},
                    {"status": "active"}
                ]
            }
        )

    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    results = []
    seen = set()

    for doc, meta, distance in zip(
        documents, metadatas, distances
    ):
        if doc in seen:
            continue
        seen.add(doc)
        results.append({
            "text": doc,
            "metadata": meta,
            "score": distance
        })

    return results
