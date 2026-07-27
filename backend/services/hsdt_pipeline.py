"""Orchestration đánh giá HSDT cho 1 nhà thầu — seam production, gọi lõi experiment dùng chung.

Toàn bộ logic ở `experiment/evaluate/pipeline.py::evaluate_hsdt` (dùng chung với CLI run_evaluate)
-> production KHÔNG đi nhánh khác CLI. Chuỗi: HSDT (pdf scan) -> ingest vision -> dò hình thức nhà
thầu -> kiểm tra thường trực -> đánh giá từng tiêu chí (gate N/A, luật liên-tài-liệu, đối chiếu
chéo) -> roll-up. no-silent-mock: proxy lỗi thì verdict "lỗi", KHÔNG bịa.
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.cached_vision import CallCache
from experiment.evaluate.ingest import PageCache
from experiment.evaluate.pipeline import evaluate_hsdt
from experiment.evaluate.rules.registry import RuleRegistry
from experiment.evaluate.schema import EvalResult, PackageContext, VendorContext

log = logging.getLogger("abes.evaluate")


async def evaluate_vendor(criteria: list[dict[str, Any]], hsdt_files: list[tuple[str, str, bytes]],
                          *, doc: str = "HSDT", vision_fn: Any | None = None,
                          vendor_ctx: VendorContext | None = None,
                          registry: RuleRegistry | None = None,
                          pkg_ctx: PackageContext | None = None,
                          cache: PageCache | None = None,
                          call_cache: CallCache | None = None) -> EvalResult:
    """HSDT + tiêu chí -> EvalResult đầy đủ (hình thức + hồ sơ + phát hiện + verdict). no-silent-mock.

    vendor_ctx: danh tính nhà thầu (gate hình thức độc lập/liên danh, lọc tài liệu dùng chung,
    luật can_vendor). registry=None -> default_registry() trong lõi. pkg_ctx: ngữ cảnh gói thầu
    đang xét (tên/mã) — luật can_pkg cần. cache: kho text đã OCR — None = luôn OCR lại.
    call_cache: kho kết quả chấm — có thì chấm lại ra y hệt lần trước.
    """
    log.info("[eval] %s: %d tiêu chí, %d file HSDT", doc, len(criteria), len(hsdt_files))
    return await evaluate_hsdt(criteria, hsdt_files, doc=doc, vision_fn=vision_fn,
                               vendor=vendor_ctx, registry=registry, pkg=pkg_ctx, cache=cache,
                               call_cache=call_cache)
