"""Tầng A — ingest HSDT scan: mỗi trang -> vision BÓC TEXT + cờ thị giác (MỘT lần).

Loại hồ sơ (loai_ho_so) ĐÃ BIẾT khi tải file (truyền vào theo từng file), KHÔNG để LLM phân loại.
Vision chỉ đọc chữ + ghi cờ chữ ký/đóng dấu.

CACHE (tùy chọn, inject qua `cache`): vision đọc ảnh là bước ĐẮT NHẤT — mỗi trang 1 call, chấm
lại một nhà thầu là OCR lại toàn bộ hồ sơ. Khóa cache lấy theo NỘI DUNG file (sha256) + dpi +
prompt ingest, nên:
- tài liệu mới / tải lại bản khác  -> khóa khác -> OCR lại (đúng thứ người dùng mong đợi);
- sửa SYS_INGEST/ingest_prompt     -> khóa khác -> OCR lại (không ăn nhầm dữ liệu prompt cũ);
- còn lại                          -> đọc cache, 0 call.

Hai bất biến của cache:
1. TRANG LỖI VISION KHÔNG BAO GIỜ ĐƯỢC GHI CACHE — proxy hỏng 1 lần mà cache lại thì text rỗng
   đóng băng vĩnh viễn, tệ hơn hẳn việc OCR lại.
2. Ảnh PNG KHÔNG nằm trong cache (nặng, và không có consumer nào ngoài ingest) — khi hit vẫn
   render lại từ PDF bằng pdf_to_images: rẻ, không tốn LLM, nên PageRecord luôn đủ field.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Protocol

from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt
from experiment.evaluate.schema import PageRecord, validate_ingest_page
from experiment.evaluate.vision import VisionFn, pdf_to_images

log = logging.getLogger("experiment.evaluate")

# dpi render PDF -> ảnh. Là MỘT NGUỒN SỰ THẬT: nơi băm khóa cache (router) phải dùng đúng giá trị
# ingest dùng, lệch một chút là cache không bao giờ hit mà không có lỗi nào báo ra.
DPI_MAC_DINH = 200


class PageCache(Protocol):
    """Kho text đã OCR theo khóa nội dung. Triển khai thật: services/ocr_cache.py (DB)."""

    def get(self, key: str) -> list[dict[str, Any]] | None: ...

    def put(self, key: str, pages: list[dict[str, Any]]) -> None: ...


def ingest_cache_key(data: bytes, dpi: int) -> str:
    """Khóa = nội dung file + dpi + prompt ingest. Prompt vào khóa để sửa prompt là cache tự hết
    hiệu lực — không phụ thuộc việc nhớ tăng số phiên bản bằng tay."""
    prompt_ver = hashlib.sha256((SYS_INGEST + ingest_prompt()).encode("utf-8")).hexdigest()[:8]
    return f"{hashlib.sha256(data).hexdigest()[:32]}-d{dpi}-p{prompt_ver}"


def _record(name: str, loai_ho_so: str, trang: int, d: dict[str, Any], png: bytes) -> PageRecord:
    return PageRecord(file=name, trang=trang, loai_ho_so=loai_ho_so, text=d.get("text", ""),
                      co_chu_ky=bool(d.get("co_chu_ky")), co_dau=bool(d.get("co_dau")), image=png)


async def _ocr_file(name: str, loai_ho_so: str, images: list[bytes],
                    vision_fn: VisionFn) -> tuple[list[PageRecord], bool]:
    """OCR từng trang -> (records, du_de_cache). du_de_cache=False nếu có BẤT KỲ trang nào lỗi."""
    records: list[PageRecord] = []
    du_de_cache = True
    for i, png in enumerate(images, 1):
        out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                              validate=validate_ingest_page)
        if out.status == "ok":
            records.append(_record(name, loai_ho_so, i, out.data, png))
        else:
            log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
            du_de_cache = False
            records.append(_record(name, loai_ho_so, i, {}, png))
    return records, du_de_cache


async def ingest_hsdt(
    files: list[tuple[str, str, bytes]], vision_fn: VisionFn, dpi: int = DPI_MAC_DINH,
    cache: PageCache | None = None,
) -> list[PageRecord]:
    """(tên_file, loai_ho_so, data pdf) -> PageRecord. loai_ho_so gán theo file; vision chỉ bóc text."""
    records: list[PageRecord] = []
    for name, loai_ho_so, data in files:
        images = pdf_to_images(data, dpi=dpi)
        key = ingest_cache_key(data, dpi)
        luu = cache.get(key) if cache is not None else None
        if luu is not None:
            log.info("[ingest] %s (%s): %d trang — dùng cache (0 call vision)", name, loai_ho_so,
                     len(luu))
            records.extend(
                _record(name, loai_ho_so, int(d.get("trang", i)), d,
                        images[i - 1] if i <= len(images) else b"")
                for i, d in enumerate(luu, 1))
            continue
        log.info("[ingest] %s (%s): %d trang", name, loai_ho_so, len(images))
        recs, du_de_cache = await _ocr_file(name, loai_ho_so, images, vision_fn)
        records.extend(recs)
        if cache is not None and du_de_cache and recs:
            cache.put(key, [{"trang": r.trang, "text": r.text, "co_chu_ky": r.co_chu_ky,
                             "co_dau": r.co_dau} for r in recs])
    return records
