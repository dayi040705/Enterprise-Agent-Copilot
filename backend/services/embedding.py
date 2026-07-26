from pathlib import Path
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parents[2]


MODEL_PATH = BASE_DIR / "models" / "bge-small-zh"


model = SentenceTransformer(
    str(MODEL_PATH)
)


def embedding_texts(texts):

    vectors = model.encode(
        texts,
        normalize_embeddings=True
    )

    return vectors.tolist()