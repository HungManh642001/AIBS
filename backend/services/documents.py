"""Trích xuất văn bản từ PDF (text/scan). OCR bằng Tesseract (vie+eng)."""
from __future__ import annotations
from typing import TypedDict
import io

import fitz  # PyMuPDF


class PageText(TypedDict):
    page: int
    text: str


def classify_pdf(data: bytes) -> str:
    """Nếu tổng text trích được < ngưỡng -> coi là PDF scan."""
    doc = fitz.open(stream=data, filetype="pdf")
    total = sum(len(page.get_text().strip()) for page in doc)
    return "pdf_text" if total >= 20 else "pdf_scan"


def extract_pdf(data: bytes) -> list[PageText]:
    doc = fitz.open(stream=data, filetype="pdf")
    return [{"page": i + 1, "text": page.get_text()} for i, page in enumerate(doc)]


def ocr_pdf(data: bytes) -> list[PageText]:
    import pytesseract
    from PIL import Image

    doc = fitz.open(stream=data, filetype="pdf")
    out: list[PageText] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="vie+eng")
        out.append({"page": i + 1, "text": text})
    return out


def extract_document(data: bytes, file_kind: str) -> list[PageText]:
    if file_kind == "pdf_scan":
        return ocr_pdf(data)
    if file_kind == "pdf_text":
        return extract_pdf(data)
    raise ValueError(f"file_kind không hỗ trợ ở đây: {file_kind}")
