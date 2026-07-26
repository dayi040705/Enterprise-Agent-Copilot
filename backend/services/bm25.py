from rank_bm25 import BM25Okapi

import jieba

from services.chroma import collection



bm25_cache = {}        # {department: BM25Okapi}

documents_cache = {}   # {department: [doc_text, ...]}

metadatas_cache = {}   # {department: [metadata, ...]}



def tokenize(text):

    """
    中文分词
    """

    return list(
        jieba.cut(text)
    )



def init_bm25(department):


    global bm25_cache
    global documents_cache
    global metadatas_cache


    data = collection.get(
        where={

            "$and":[

                {
                    "department": department
                },

                {
                    "status": "active"
                }

            ]

        }

    )



    documents_cache[department] = data["documents"]

    metadatas_cache[department] = data["metadatas"]



    tokenized_docs = [

        tokenize(doc)

        for doc in documents_cache[department]

    ]


    bm25_cache[department] = BM25Okapi(
        tokenized_docs
    )



def bm25_search(

        question,
        department,
        top_k=20

):
    global bm25_cache


    if department not in bm25_cache:

        init_bm25(
            department
        )


    bm25 = bm25_cache[department]

    documents = documents_cache[department]

    metadatas = metadatas_cache[department]




    query_tokens = tokenize(
        question
    )



    scores = bm25.get_scores(
        query_tokens
    )



    results=[]



    indexes = sorted(

        range(len(scores)),

        key=lambda i: scores[i],

        reverse=True

    )



    for i in indexes[:top_k]:


        results.append(

            {

            "text":
            documents[i],


            "metadata":
            metadatas[i],


            "score":
            scores[i]

            }

        )


    return results
