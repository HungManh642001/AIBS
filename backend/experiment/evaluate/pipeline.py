"""Lõi đánh giá HSDT dùng chung — MỘT đường cho CLI (run_evaluate) lẫn production (hsdt_pipeline).

Toàn bộ lịch sử bug (`fired`, `doi_chieu_hsdt`, `ho_so_can[0]`) đều sinh từ việc production đi
nhánh khác CLI. Đặt logic dựng EvalResult ở ĐÂY, cả hai gọi chung -> không còn hai đường phân kỳ.
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.route import inventory_pages, pages_by_type
from experiment.evaluate.rules.registry import RuleRegistry, default_registry, dispatch_standing
from experiment.evaluate.schema import EvalResult, VendorContext
from experiment.evaluate.vendor_profile import detect_vendor_profile
from experiment.evaluate.vision import VisionFn, default_vision_fn

log = logging.getLogger("experiment.evaluate")


async def evaluate_hsdt(criteria: list[dict[str, Any]], hsdt_files: list[tuple[str, str, bytes]],
                        *, doc: str = "HSDT", vision_fn: VisionFn | None = None,
                        vendor: VendorContext | None = None,
                        registry: RuleRegistry | None = None) -> EvalResult:
    """HSDT (pdf scan) + tiêu chí -> EvalResult đầy đủ (verdict + hình thức + hồ sơ + phát hiện).

    hsdt_files: (tên_file, loai_ho_so [mã catalog], data pdf). vendor: danh tính nhà thầu (gate N/A,
    lọc tài liệu dùng chung, luật can_vendor). registry: mặc định = default_registry().
    """
    vision_fn = vision_fn or default_vision_fn
    registry = registry if registry is not None else default_registry()

    pages = await ingest_hsdt(hsdt_files, vision_fn)
    by_type = pages_by_type(pages)   # build 1 lần cho mọi luật

    profile = await detect_vendor_profile(pages, vision_fn, vendor=vendor)
    log.info("[eval] %s: hình thức nhà thầu %s (căn cứ: %s)", doc,
             profile.hinh_thuc or "không rõ", profile.nguon)
    if profile.mau_thuan:
        log.warning("[eval] %s: ⚠️ MÂU THUẪN hình thức nhà thầu: %s", doc, profile.ghi_chu)

    # Kiểm tra thường trực: 1 lần/nhà thầu, KHÔNG gắn tiêu chí, không vào roll-up.
    phat_hien = await dispatch_standing(registry, by_type, vendor, vision_fn)
    result = EvalResult(doc=doc, vendor=vendor, vendor_profile=profile,
                        ho_so_nhan_duoc=inventory_pages(pages), phat_hien_bo_sung=phat_hien)
    for c in criteria:
        result.criteria.append(await evaluate_criterion(
            c, pages, vision_fn, registry=registry, vendor_ctx=vendor, profile=profile,
            by_type=by_type))
    log.info("[eval] %s: %s", doc, result.summary)
    return result
