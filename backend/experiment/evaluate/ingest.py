"""Tầng A — ingest HSDT scan: mỗi trang -> vision BÓC TEXT + cờ thị giác (MỘT lần).

Loại hồ sơ (loai_ho_so) ĐÃ BIẾT khi tải file (truyền vào theo từng file), KHÔNG để LLM phân loại.
Vision chỉ đọc chữ + ghi cờ chữ ký/đóng dấu.
"""
from __future__ import annotations

import logging

from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt
from experiment.evaluate.schema import PageRecord, validate_ingest_page
from experiment.evaluate.vision import VisionFn, pdf_to_images

log = logging.getLogger("experiment.evaluate")


async def ingest_hsdt(
    files: list[tuple[str, str, bytes]], vision_fn: VisionFn, dpi: int = 200
) -> list[PageRecord]:
    """(tên_file, loai_ho_so, data pdf) -> PageRecord. loai_ho_so gán theo file; vision chỉ bóc text."""
    records: list[PageRecord] = []
    for name, loai_ho_so, data in files:
        images = pdf_to_images(data, dpi=dpi)
        log.info("[ingest] %s (%s): %d trang", name, loai_ho_so, len(images))
        for i, png in enumerate(images, 1):
            out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                                  validate=validate_ingest_page)
            if out.status == "ok":
                d = out.data
                rec = PageRecord(file=name, trang=i, loai_ho_so=loai_ho_so, text=d.get("text", ""),
                                 co_chu_ky=bool(d.get("co_chu_ky")), co_dau=bool(d.get("co_dau")),
                                 image=png)
            else:
                log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
                rec = PageRecord(file=name, trang=i, loai_ho_so=loai_ho_so, text="",
                                 co_chu_ky=False, co_dau=False, image=png)
            records.append(rec)
    return records
