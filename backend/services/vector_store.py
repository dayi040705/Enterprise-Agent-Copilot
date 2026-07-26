import chromadb


client = chromadb.PersistentClient(
    path="./chroma_db"
)


collection = client.get_or_create_collection(
    name="enterprise_documents"
)



def add_documents(
        documents,
        embeddings,
        metadatas
):

    ids = [
        str(i)
        for i in range(len(documents))
    ]


    collection.add(

        documents=documents,

        embeddings=embeddings,

        metadatas=metadatas,

        ids=ids

    )



def search(
        query_embedding,
        top_k=3
):

    result = collection.query(

        query_embeddings=[
            query_embedding
        ],

        n_results=top_k,

        include=[
            "documents",
            "metadatas",
            "distances"
        ]

    )


    return result