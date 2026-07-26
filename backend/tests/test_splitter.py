"""测试: 语义分块器"""

def test_empty_text():
    """空文本不应崩溃, 返回空列表"""
    from services.splitter import split_text
    result = split_text([{"text": "", "page": 1}], "test.pdf")
    assert isinstance(result, list)
    assert len(result) == 0


def test_short_text():
    """短文本 (小于 max_chunk_size) 应该保持完整, 只产生 1 个 chunk"""
    from services.splitter import split_text
    text = "这是一段短文本，用于测试。"
    result = split_text([{"text": text, "page": 1}], "test.pdf")
    assert len(result) == 1
    assert text in result[0]["text"]


def test_metadata_fields():
    """每个 chunk 的 metadata 必须包含所有必要字段"""
    from services.splitter import split_text
    result = split_text(
        [{"text": "测试文本。", "page": 3}],
        filename="员工手册.pdf",
        department="HR",
        version=2,
        status="active"
    )
    meta = result[0]["metadata"]
    assert meta["filename"] == "员工手册.pdf"
    assert meta["page"] == 3
    assert meta["department"] == "HR"
    assert meta["version"] == 2
    assert meta["status"] == "active"
    assert "chunk_id" in meta


def test_multi_page():
    """多页文档应产生多个 chunk"""
    from services.splitter import split_text
    pages = [
        {"text": "第一页。第二句。第三句。第四句。第五句。第六句。第七句。第八句。", "page": 1},
        {"text": "第二页内容。", "page": 2},
    ]
    result = split_text(pages, "test.pdf")
    assert len(result) >= 2
    pages_in_meta = set(r["metadata"]["page"] for r in result)
    assert 1 in pages_in_meta
    assert 2 in pages_in_meta
