import chromadb
import uuid
from pathlib import Path

from services.embedding import embedding_texts


# 锚定 backend/chroma_db 绝对路径: 与启动目录无关, 避免数据分裂到其他位置
BACKEND_DIR = Path(__file__).resolve().parents[1]
CHROMA_PATH = str(BACKEND_DIR / "chroma_db")

client = chromadb.PersistentClient(
    path=CHROMA_PATH
)


collection = client.get_or_create_collection(
    name="knowledge"
)



def add_documents(chunks):


    # 1. 去重

    unique_chunks = []

    seen = set()


    for chunk in chunks:

        if chunk["text"] not in seen:

            unique_chunks.append(chunk)

            seen.add(chunk["text"])



    texts = []

    metadatas = []


    # 2. 提取文本和metadata

    for chunk in unique_chunks:

        texts.append(
            chunk["text"]
        )

        metadatas.append(
            chunk["metadata"]
        )


    # 3. embedding

    vectors = embedding_texts(
        texts
    )


    # 4. 写入Chroma

    collection.add(

        documents=texts,

        embeddings=vectors,

        metadatas=metadatas,

        ids=[
            str(uuid.uuid4())
            for _ in texts
        ]

    )
def delete_documents(
        filename,
        version
):

    collection.delete(

        where={

            "$and":[

                {
                    "filename":filename
                },

                {
                    "version":version
                }

            ]

        }

    )