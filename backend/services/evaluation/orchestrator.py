"""Điều phối đánh giá 4 module cho từng nhà thầu, tổng hợp & xếp hạng."""
from __future__ import annotations
from decimal import Decimal
from typing import Any, TypedDict

from services.evaluation.base import EvalResult
from services.evaluation.legality import evaluate_legality
from services.evaluation.capacity import evaluate_capacity
from services.evaluation.technical import evaluate_technical
from services.evaluation.financial import (
    FinancialResult, recalc_price_table, extract_price_rows,
)


class VendorEvaluation(TypedDict):
    legality: list[EvalResult]
    capacity: list[EvalResult]
    technical: list[EvalResult]
    financial: FinancialResult
    technical_score: float
    passed_legality: bool


def _weighted(technical: list[EvalResult], criteria: list[dict[str, Any]]) -> float:
    if not technical:
        return 0.0
    weights = {c["ten"]: float(c.get("trong_so") or 0) for c in criteria}
    total_w = sum(weights.get(r["criteria_ten"], 0) for r in technical)
    if total_w <= 0:
        return sum(r["score"] for r in technical) / len(technical)
    return sum(r["score"] * weights.get(r["criteria_ten"], 0) for r in technical) / total_w


async def evaluate_vendor(
    criteria: list[dict[str, Any]],
    hsdt_pages: list[dict[str, Any]],
    price_pages: list[dict[str, Any]],
) -> VendorEvaluation:
    legality = await evaluate_legality(criteria, hsdt_pages)
    capacity = await evaluate_capacity(criteria, hsdt_pages)
    technical = await evaluate_technical(criteria, hsdt_pages)
    financial = recalc_price_table(extract_price_rows(price_pages))
    passed = all(r["result"] != "FAIL" for r in legality + capacity)
    return VendorEvaluation(
        legality=legality, capacity=capacity, technical=technical,
        financial=financial, technical_score=_weighted(technical, criteria),
        passed_legality=passed,
    )


def rank_vendors(evals: dict[int, VendorEvaluation]) -> list[dict[str, Any]]:
    eligible = [
        {"vendor_id": vid, "evaluated_price": ev["financial"]["evaluated_price"],
         "technical_score": ev["technical_score"], "eligible": True}
        for vid, ev in evals.items() if ev["passed_legality"]
    ]
    eligible.sort(key=lambda r: r["evaluated_price"])
    for i, r in enumerate(eligible, start=1):
        r["rank"] = i
    ineligible = [
        {"vendor_id": vid, "evaluated_price": ev["financial"]["evaluated_price"],
         "technical_score": ev["technical_score"], "eligible": False, "rank": None}
        for vid, ev in evals.items() if not ev["passed_legality"]
    ]
    return eligible + ineligible
