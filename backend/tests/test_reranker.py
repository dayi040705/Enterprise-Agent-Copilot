"""测试: Reranker 精排"""
import pytest


def _can_import_reranker():
    """检查能否加载 reranker 模型 (需要网络或缓存)"""
    try:
        from services.reranker import rerank
        return True
    except Exception:
        return False


# 网络不可用时跳过 reranker 相关测试
NEEDS_RERANKER = pytest.mark.skipif(
    not _can_import_reranker(),
    reason="bge-reranker-base 模型不可用 (网络问题或未下载)"
)


@NEEDS_RERANKER
def test_rerank_empty_input():
    """空文档列表应安全返回空列表 (不能崩溃)"""
    from services.reranker import rerank
    result = rerank("问题", [], top_k=5, score_threshold=-2)
    assert result == []


@NEEDS_RERANKER
def test_rerank_scoring():
    """Reranker 应对相关文档打高分, 不相关文档打低分"""
    from services.reranker import reranker

    pairs = [
        ["员工请假流程是什么？", "员工填写请假申请单，提交直属领导审批。"],
        ["员工请假流程是什么？", "今天天气很好适合出去玩。"],
    ]
    scores = reranker.compute_score(pairs)

    assert len(scores) == 2
    assert scores[0] > scores[1], \
        f"相关文档分 ({scores[0]:.2f}) 应该 > 不相关文档分 ({scores[1]:.2f})"


@NEEDS_RERANKER
def test_rerank_filter_and_top_k():
    """rerank 函数应正确过滤低分文档并截断 top_k"""
    from services.reranker import rerank

    documents = [
        {"text": "相关文档1", "metadata": {}, "score": 0},
        {"text": "相关文档2", "metadata": {}, "score": 0},
        {"text": "不相关1", "metadata": {}, "score": 0},
        {"text": "不相关2", "metadata": {}, "score": 0},
        {"text": "不相关3", "metadata": {}, "score": 0},
    ]

    result = rerank("测试问题", documents, top_k=3, score_threshold=-2)
    assert len(result) <= 3, f"期望 <=3, 实际 {len(result)}"
