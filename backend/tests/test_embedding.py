"""测试: Embedding 模型"""
import numpy as np


def test_embedding_dimension():
    """bge-small-zh 输出必须是 512 维"""
    from services.embedding import embedding_texts

    vectors = embedding_texts(["测试文本"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 512, f"期望 512 维, 实际 {len(vectors[0])} 维"


def test_embedding_normalized():
    """输出向量应该归一化 (L2 norm ≈ 1.0)"""
    from services.embedding import embedding_texts

    vectors = embedding_texts(["测试文本", "另一段文本"])
    for vec in vectors:
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01, f"L2 norm = {norm}, 应该是 1.0"


def test_embedding_batch():
    """批量 embedding 应该返回相同数量的向量"""
    from services.embedding import embedding_texts

    texts = ["文本1", "文本2", "文本3"]
    vectors = embedding_texts(texts)
    assert len(vectors) == len(texts)
