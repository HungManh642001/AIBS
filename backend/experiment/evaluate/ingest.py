"""Tầng A — ingest HSDT scan: mỗi trang -> vision bóc text + phân loại + cờ thị giác (MỘT lần)."""
from __future__ import annotations

import logging

from experiment.evaluate.prompts import SYS_INGEST, ingest_prompt
from experiment.evaluate.schema import PageRecord, validate_ingest_page
from experiment.evaluate.vision import VisionFn, pdf_to_images

log = logging.getLogger("experiment.evaluate")


async def ingest_hsdt(
    files: list[tuple[str, bytes]], vision_fn: VisionFn, dpi: int = 200
) -> list[PageRecord]:
    """(tên_file, data pdf) -> danh sách PageRecord (giữ ảnh PNG để tầng evaluate soi thị giác)."""
    records: list[PageRecord] = []
    for name, data in files:
        images = pdf_to_images(data, dpi=dpi)
        log.info("[ingest] %s: %d trang", name, len(images))
        for i, png in enumerate(images, 1):
            out = await vision_fn(SYS_INGEST, ingest_prompt(), images=[png],
                                  validate=validate_ingest_page)
            if out.status == "ok":
                d = out.data
                rec = PageRecord(file=name, trang=i, loai_ho_so=d.get("loai_ho_so", "khac"),
                                 text=d.get("text", ""), co_chu_ky=bool(d.get("co_chu_ky")),
                                 co_dau=bool(d.get("co_dau")), image=png)
            else:
                log.warning("[ingest] %s tr%d lỗi vision: %s", name, i, out.error)
                rec = PageRecord(file=name, trang=i, loai_ho_so="khac", text="",
                                 co_chu_ky=False, co_dau=False, image=png)
            records.append(rec)
    return records
