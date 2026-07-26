from FlagEmbedding import FlagReranker


reranker = FlagReranker(
    "BAAI/bge-reranker-base",
    use_fp16=False
)



def rerank(
        question,
        documents,
        top_k=5,
        score_threshold=2
):

    if not documents:
        return []

    pairs = []


    for doc in documents:

        pairs.append(
            [
                question,
                doc["text"]
            ]
        )


    scores = reranker.compute_score(
        pairs
    )


    results=[]


    for doc, score in zip(
        documents,
        scores
    ):

        doc["score"] = score

        results.append(doc)



    # 先按照rerank分数排序
    results.sort(
        key=lambda x:x["score"],
        reverse=True
    )



    # 再过滤
    filtered = [

        doc

        for doc in results

        if doc["score"] >= score_threshold

    ]



    # 最后取top_k

    return filtered[:top_k]