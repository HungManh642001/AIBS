"""Kiểu dữ liệu & helper dùng chung cho các module đánh giá."""
from __future__ import annotations
from typing import Any, TypedDict

from services.ai_client import ai_json


class EvalResult(TypedDict):
    criteria_ten: str
    result: str          # PASS | FAIL | PARTIAL
    score: float
    evidence: str
    page_ref: list[int]
    note: str
    ai_model: str


def _clamp(v: Any) -> float:
    try:
        return max(0.0, min(100.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


async def eval_one(
    system: str, criteria: dict[str, Any], content: str, mock_key: str
) -> EvalResult:
    prompt = (
        f"Tiêu chí: {criteria.get('ten')}\n"
        f"Yêu cầu HSMT: {criteria.get('yeu_cau', '')}\n"
        f"Nội dung HSDT:\n{content[:8000]}\n\n"
        'Trả về JSON: {"result":"PASS|FAIL|PARTIAL","score":0-100,'
        '"evidence":"...","page_ref":[...],"note":"..."}'
    )
    data = await ai_json(system, prompt, mock_key=mock_key)
    result = data.get("result", "PARTIAL")
    if result not in {"PASS", "FAIL", "PARTIAL"}:
        result = "PARTIAL"
    return EvalResult(
        criteria_ten=criteria.get("ten", ""),
        result=result,
        score=_clamp(data.get("score", 0)),
        evidence=data.get("evidence") or "Không có dẫn chứng",
        page_ref=data.get("page_ref") or [],
        note=data.get("note", ""),
        ai_model=data.get("_model", ""),
    )
