"""Kho cache kết quả CHẤM trên DB — seam giữa lõi experiment (không biết DB) và production.

Lõi chỉ biết giao thức `CallCache` (get/put theo khóa băm từ đầu vào); adapter này gắn thêm phạm
vi gói/nhà thầu để xóa có chọn lọc khi muốn ép AI chấm lại từ đầu.

Tách theo nhà thầu dù khóa đã băm cả prompt: hai nhà thầu không bao giờ dùng chung một kết quả,
và khi chấm lại riêng một nhà thầu thì chỉ xóa đúng phần của họ.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import models

log = logging.getLogger("abes.evaluate")


class DbCallCache:
    """CallCache lưu trên bảng ai_call_cache, phạm vi (gói, nhà thầu)."""

    def __init__(self, db: Session, package_id: int, vendor_id: int | None):
        self._db = db
        self._pkg = package_id
        self._vendor = vendor_id

    def _row(self, key: str) -> models.AiCallCache | None:
        return self._db.scalars(
            select(models.AiCallCache).where(
                models.AiCallCache.package_id == self._pkg,
                models.AiCallCache.vendor_id == self._vendor,
                models.AiCallCache.khoa == key)).first()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._row(key)
        return dict(row.data) if row is not None and row.data else None

    def put(self, key: str, data: dict[str, Any]) -> None:
        row = self._row(key)
        if row is None:
            row = models.AiCallCache(package_id=self._pkg, vendor_id=self._vendor, khoa=key)
            self._db.add(row)
        row.data = dict(data)
        self._db.commit()


def xoa_ai_cache(db: Session, package_id: int, *, vendor_id: int | None = None) -> int:
    """Xóa cache chấm để lần sau hỏi lại model. Trả SỐ bản ghi đã xóa."""
    q = select(models.AiCallCache).where(models.AiCallCache.package_id == package_id)
    if vendor_id is not None:
        q = q.where(models.AiCallCache.vendor_id == vendor_id)
    rows = db.scalars(q).all()
    for r in rows:
        db.delete(r)
    db.commit()
    log.info("[ai-cache] xóa %d kết quả chấm (gói %s, nhà thầu %s)", len(rows), package_id,
             vendor_id)
    return len(rows)
