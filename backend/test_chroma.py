from services.embedding import embedding_text
from services.vector_store import add_documents,search


texts=[
    "员工请假需要提前申请",
    "报销需要提交发票",
    "公司下午六点下班"
]


metadatas=[
    {
        "source":"员工管理制度.pdf",
        "page":1,
        "chunk_id":0
    },

    {
        "source":"财务报销制度.pdf",
        "page":2,
        "chunk_id":1
    },

    {
        "source":"考勤制度.pdf",
        "page":1,
        "chunk_id":2    
    }
]


vectors=[
    embedding_text(text)
    for text in texts
]


add_documents(
    texts,
    vectors,
    metadatas
)


query="怎么申请假期"


query_vector=embedding_text(query)


result=search(query_vector)


print(result)