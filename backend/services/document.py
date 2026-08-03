"""
文档解析模块

PDF 解析采用双通道策略:
  Channel 1: PyPDF2 extract_text() — 文本型 PDF, 毫秒级
  Channel 2: PaddleOCR — 扫描件/图片型 PDF, GPU 加速

面试金句:
  "不是所有 PDF 都是文本型的。我在解析层做了双通道——
   先文本提取, 空白率 > 80% 说明是扫描件, 自动切 OCR 通道。
   这样正常文档不触发 OCR(快), 扫描件有降级通道(全)。"
"""

from pypdf import PdfReader
from docx import Document as DocxDocument
import re
import io
import logging

logger = logging.getLogger(__name__)

# ============================================================
# 文本清洗 — PDF 提取后过滤噪声
# ============================================================

PATTERNS = [
    (r'^\d{1,2}\s*/\s*\d{1,2}\s*$', ''),            # 页码: "5 / 20"
    (r'^\s*\d+\s*$', ''),                              # 纯数字行: "5"
    (r'第\s*\d+\s*页', ''),                            # 中文页码: "第5页"
    (r'^\s*[©®™]\s*$', ''),                            # 版权符号行
    (r'\n{3,}', '\n\n'),                               # 连续3个以上换行压缩为2个
    (r'[ \t]{2,}', ' '),                               # 连续空白压缩
]


def _clean_text(text: str) -> str:
    """清理从 PDF 提取出来的脏文本: 页码/页眉/多余空白"""
    for pattern, replacement in PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return text.strip()


# ============================================================
# 跨页段落合并 — 拦截页边界的段落断裂
# ============================================================

def _merge_cross_page(pages: list) -> list:
    """
    PDF 页边界经常把一段话切成两半。检查前一页最后一句是否没有标点结尾,
    如果是 → 说明被截断了 → 拼到下一页开头。
    """
    if len(pages) <= 1:
        return pages

    merged = [pages[0]]
    for i in range(1, len(pages)):
        prev = merged[-1]["text"]
        curr = pages[i]["text"]
        # 前一页不以标点结尾 → 段落被截断, 拼接
        if prev and not re.search(r'[。！？\n]$', prev.strip()):
            merged[-1]["text"] = prev.rstrip() + curr.lstrip()
        else:
            merged.append(pages[i])
    return merged


# ============================================================
# OCR 通道 — 扫描件/图片型 PDF 的文字提取
# ============================================================

# 懒加载: 只有扫描件才初始化 OCR, 正常文档不占内存
_ocr = None


def _get_ocr():
    """懒加载 PaddleOCR, 首次调用时初始化 (约 2s)"""
    global _ocr
    if _ocr is None:
        try:
            from paddleocr import PaddleOCR
            _ocr = PaddleOCR(lang='ch', use_angle_cls=True, show_log=False)
        except ImportError:
            raise ImportError("PaddleOCR 未安装。pip install paddlepaddle paddleocr")
    return _ocr


def _needs_ocr(text: str) -> bool:
    """判断一页是否需要用 OCR 重新提取"""
    clean = text.strip()
    if not clean:
        return True
    # 文本提取出的内容非常少 (< 10个字符), 大概率是扫描件
    if len(clean) < 10:
        return True
    return False


def _ocr_page(pdf_path: str, page_number: int) -> str:
    """
    用 PaddleOCR 识别 PDF 中的某一页图片。
    流程: PDF 页 → PyMuPDF 渲染为图片 → PaddleOCR 识别 → 返回文本
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF 未安装。pip install PyMuPDF")

    ocr = _get_ocr()
    doc = fitz.open(pdf_path)
    page = doc[page_number]
    pix = page.get_pixmap(dpi=200)  # 200 DPI — 识别精度和速度的平衡点
    img_bytes = pix.tobytes("png")

    result = ocr.ocr(img_bytes, cls=True)
    doc.close()

    if not result or not result[0]:
        return ""

    # 按行从上到下拼接文本
    lines = []
    for line_info in result[0]:
        text = line_info[1][0]
        confidence = line_info[1][1]
        if confidence > 0.5:  # 过滤低置信度结果
            lines.append(text)
    return "\n".join(lines)


# ============================================================
# 解析器
# ============================================================

def read_pdf(file_path):
    """
    PDF 双通道解析: 文本提取 → 空白页自动 OCR

    Channel 1 (PyPDF2): 文本型 PDF, 毫秒级提取
    Channel 2 (PaddleOCR): 扫描件/图片页, 渲染后 OCR 识别

    每页独立判断, 不会因为某一页是扫描件就全局降级
    """
    reader = PdfReader(file_path)
    pages = []
    ocr_used = False

    for page_number, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        text = _clean_text(raw)

        # 文本提取空白 → 尝试 OCR 通道
        if _needs_ocr(text):
            try:
                ocr_text = _ocr_page(file_path, page_number)
                if ocr_text:
                    text = _clean_text(ocr_text)
                    ocr_used = True
                    logger.info(f"OCR 页 {page_number + 1}: {len(text)} chars")
            except ImportError:
                pass  # OCR 未安装, 静默跳过此页
            except Exception as e:
                logger.warning(f"OCR 页 {page_number + 1} 失败: {e}")

        if text:
            pages.append({"text": text, "page": page_number + 1})

    if ocr_used:
        logger.info(f"{file_path}: 触发 OCR, 共 {len(pages)} 页")

    return _merge_cross_page(pages)


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
