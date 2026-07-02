"""Orchestration đánh giá HSDT cho 1 nhà thầu — tái dùng experiment/evaluate (read-only).

Chuỗi: HSDT (pdf scan) -> ingest vision (bóc text + cờ chữ ký/dấu, MỘT lần/trang) -> đánh giá
từng tiêu chí (route nội dung -> trang, đối chiếu chuẩn HSMT) -> roll-up (tien_quyet + không đạt ->
loại). no-silent-mock: proxy lỗi thì verdict "lỗi" (trong evaluate.py), KHÔNG bịa.
"""
from __future__ import annotations

import logging
from typing import Any

from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.ingest import ingest_hsdt
from experiment.evaluate.schema import EvalResult
from experiment.evaluate.vision import default_vision_fn

log = logging.getLogger("abes.evaluate")


async def evaluate_vendor(criteria: list[dict[str, Any]], hsdt_files: list[tuple[str, str, bytes]],
                          doc: str = "HSDT", vision_fn: Any | None = None) -> EvalResult:
    """HSDT (pdf scan) + tiêu chí -> EvalResult (verdict mỗi nội dung + roll-up). no-silent-mock."""
    vision_fn = vision_fn or default_vision_fn
    log.info("[eval] %s: %d tiêu chí, %d file HSDT", doc, len(criteria), len(hsdt_files))
    pages = await ingest_hsdt(hsdt_files, vision_fn)
    log.info("[eval] %s: ingest xong %d trang", doc, len(pages))
    result = EvalResult(doc=doc)
    for c in criteria:
        result.criteria.append(await evaluate_criterion(c, pages, vision_fn))
    log.info("[eval] %s: %s", doc, result.summary)
    return result
