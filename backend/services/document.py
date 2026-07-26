from pypdf import PdfReader
from docx import Document as DocxDocument


def read_pdf(file_path):
    """解析 PDF 文件, 逐页提取文本"""
    reader = PdfReader(file_path)
    pages = []
    for page_number, page in enumerate(reader.pages):
        text = page.extract_text()
        pages.append({"text": text, "page": page_number + 1})
    return pages


def read_docx(file_path):
    """解析 Word 文档, 按段落分组为虚拟页"""
    doc = DocxDocument(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)

    # Word 没有页码概念, 每 15 段合为一"页"
    pages = []
    chunk_size = 15
    para_chunks = [paragraphs[i:i+chunk_size] for i in range(0, len(paragraphs), chunk_size)]
    for i, chunk in enumerate(para_chunks):
        pages.append({"text": "\n".join(chunk), "page": i + 1})

    return pages if pages else [{"text": text, "page": 1}]


def read_txt(file_path):
    """读取纯文本文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return [{"text": f.read(), "page": 1}]


def read_md(file_path):
    """读取 Markdown 文件 (保留原始格式)"""
    with open(file_path, "r", encoding="utf-8") as f:
        return [{"text": f.read(), "page": 1}]


def load_document(file_path):
    """根据文件后缀自动选择解析器"""
    ext = file_path.lower()

    if ext.endswith(".pdf"):
        return read_pdf(file_path)
    elif ext.endswith(".docx"):
        return read_docx(file_path)
    elif ext.endswith(".md") or ext.endswith(".markdown"):
        return read_md(file_path)
    elif ext.endswith(".txt"):
        return read_txt(file_path)
    else:
        raise Exception(f"不支持的文件格式: {file_path}")
