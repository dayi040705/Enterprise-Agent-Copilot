import chromadb
import uuid

from services.embedding import embedding_texts


client = chromadb.PersistentClient(
    path="./chroma_db"
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