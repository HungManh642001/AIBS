"""Cache text vision-OCR trên DB — seam giữa lõi experiment (không biết DB) và production.

Lõi `experiment/evaluate/ingest.py` chỉ biết giao thức `PageCache` (get/put theo khóa nội dung);
adapter này gắn khóa đó vào đúng `tender_document` để cache sống/chết cùng tài liệu (xóa tài liệu
là cache đi theo, không để lại rác).

Bản đồ {khóa: doc_id} do nơi ĐỌC file dựng sẵn (router evaluate) — chỗ đó vừa có bytes để băm vừa
có id tài liệu, nên adapter không phải tự đi đọc lại file.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import models

log = logging.getLogger("abes.evaluate")


class DocumentOcrCache:
    """PageCache lưu trên tender_document. Khóa lạ (không có trong bản đồ) -> bỏ qua, KHÔNG nổ."""

    def __init__(self, db: Session, khoa_theo_doc: dict[str, int]):
        self._db = db
        self._map = dict(khoa_theo_doc)

    def _doc(self, key: str) -> models.TenderDocument | None:
        doc_id = self._map.get(key)
        return self._db.get(models.TenderDocument, doc_id) if doc_id is not None else None

    def get(self, key: str) -> list[dict[str, Any]] | None:
        doc = self._doc(key)
        if doc is None or doc.ocr_key != key or not doc.ocr_pages:
            return None      # khóa lệch = file đã đổi (hoặc prompt/dpi đổi) -> phải OCR lại
        return list(doc.ocr_pages)

    def put(self, key: str, pages: list[dict[str, Any]]) -> None:
        doc = self._doc(key)
        if doc is None:
            return
        doc.ocr_key = key
        doc.ocr_pages = list(pages)
        self._db.commit()
        log.info("[ocr-cache] lưu %d trang cho tài liệu %s", len(pages), doc.file_path)


def xoa_cache(db: Session, package_id: int, *, vendor_id: int | None = None,
              doc_id: int | None = None) -> int:
    """Xóa cache để lần chấm sau OCR lại. Trả SỐ tài liệu thực sự bị xóa cache.

    Lọc dần: cả gói -> 1 nhà thầu -> 1 tài liệu. Dùng khi nghi OCR đọc sai hoặc vừa đổi model.
    """
    q = select(models.TenderDocument).where(models.TenderDocument.package_id == package_id)
    if vendor_id is not None:
        q = q.where(models.TenderDocument.vendor_id == vendor_id)
    if doc_id is not None:
        q = q.where(models.TenderDocument.id == doc_id)
    n = 0
    for doc in db.scalars(q).all():
        if not doc.ocr_key and not doc.ocr_pages:
            continue
        doc.ocr_key = ""
        doc.ocr_pages = []
        n += 1
    db.commit()
    log.info("[ocr-cache] xóa cache %d tài liệu (gói %s, nhà thầu %s, tài liệu %s)",
             n, package_id, vendor_id, doc_id)
    return n
