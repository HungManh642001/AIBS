"""Lõi đánh giá HSDT dùng chung — MỘT đường cho CLI (run_evaluate) lẫn production (hsdt_pipeline).

Toàn bộ lịch sử bug (`fired`, `doi_chieu_hsdt`, `ho_so_can[0]`) đều sinh từ việc production đi
nhánh khác CLI. Đặt logic dựng EvalResult ở ĐÂY, cả hai gọi chung -> không còn hai đường phân kỳ.
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.cached_vision import CachedVision, CallCache
from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import PageCache, ingest_hsdt
from experiment.evaluate.route import inventory_pages, pages_by_type
from experiment.evaluate.rules.registry import RuleRegistry, default_registry, dispatch_standing
from experiment.evaluate.schema import EvalResult, PackageContext, VendorContext
from experiment.evaluate.vendor_profile import detect_vendor_profile
from experiment.evaluate.vision import VisionFn, default_vision_fn

log = logging.getLogger("experiment.evaluate")


async def evaluate_hsdt(criteria: list[dict[str, Any]], hsdt_files: list[tuple[str, str, bytes]],
                        *, doc: str = "HSDT", vision_fn: VisionFn | None = None,
                        vendor: VendorContext | None = None,
                        registry: RuleRegistry | None = None,
                        pkg: PackageContext | None = None,
                        cache: PageCache | None = None,
                        call_cache: CallCache | None = None) -> EvalResult:
    """HSDT (pdf scan) + tiêu chí -> EvalResult đầy đủ (verdict + hình thức + hồ sơ + phát hiện).

    hsdt_files: (tên_file, loai_ho_so [mã catalog], data pdf). vendor: danh tính nhà thầu (gate N/A,
    lọc tài liệu dùng chung, luật can_vendor). registry: mặc định = default_registry().
    pkg: ngữ cảnh gói thầu đang xét (tên/mã số) — luật can_pkg cần.
    cache: kho text đã OCR (xem ingest.PageCache) — None = luôn OCR lại như trước.
    call_cache: kho kết quả CHẤM (xem cached_vision.CallCache) — có thì chấm lại ra y hệt, 0 call.
    """
    vision_fn = vision_fn or default_vision_fn
    if call_cache is not None:
        # Bọc MỘT lần ở đây là phủ mọi call chấm (eval, dò hình thức, mọi luật).
        vision_fn = CachedVision(vision_fn, call_cache)
    registry = registry if registry is not None else default_registry()

    pages = await ingest_hsdt(hsdt_files, vision_fn, cache=cache)
    by_type = pages_by_type(pages)   # build 1 lần cho mọi luật

    profile = await detect_vendor_profile(pages, vision_fn, vendor=vendor)
    log.info("[eval] %s: hình thức nhà thầu %s (căn cứ: %s)", doc,
             profile.hinh_thuc or "không rõ", profile.nguon)
    if profile.mau_thuan:
        log.warning("[eval] %s: ⚠️ MÂU THUẪN hình thức nhà thầu: %s", doc, profile.ghi_chu)

    # Kiểm tra thường trực: 1 lần/nhà thầu, KHÔNG gắn tiêu chí, không vào roll-up.
    phat_hien = await dispatch_standing(registry, by_type, vendor, vision_fn, pkg=pkg)
    result = EvalResult(doc=doc, vendor=vendor, vendor_profile=profile,
                        ho_so_nhan_duoc=inventory_pages(pages), phat_hien_bo_sung=phat_hien)
    for c in criteria:
        result.criteria.append(await evaluate_criterion(
            c, pages, vision_fn, registry=registry, vendor_ctx=vendor, profile=profile,
            by_type=by_type))
    log.info("[eval] %s: %s", doc, result.summary)
    return result
