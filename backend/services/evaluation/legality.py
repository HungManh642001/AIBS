"""F03 - Đánh giá Tính Hợp Lệ."""
from __future__ import annotations
from typing import Any

from services.evaluation.base import EvalResult, eval_one, evaluate_criterion, aggregate_subresults

_SYS = (
    "Bạn là chuyên gia đánh giá tính hợp lệ HSDT theo Luật Đấu thầu Việt Nam. "
    "Chỉ trả về JSON."
)


def _content(pages: list[dict[str, Any]]) -> str:
    return "\n".join(f"[Trang {p['page']}] {p['text']}" for p in pages)


async def evaluate_legality(
    criteria: list[dict[str, Any]], hsdt_pages: list[dict[str, Any]]
) -> list[EvalResult]:
    content = _content(hsdt_pages)
    out: list[EvalResult] = []
    for c in criteria:
        if c.get("nhom") == "hop_le":
            out.append(await eval_one(_SYS, c, content, mock_key="eval_legality"))
    return out


async def evaluate_legality_routed(
    criteria: list[dict[str, Any]], artifact_content_map: dict[str, str], max_page: int = 0
) -> list[dict[str, Any]]:
    """Đánh giá tiêu chí hợp lệ theo artifact routing (chỉ nhóm hop_le)."""
    out: list[dict[str, Any]] = []
    for c in criteria:
        if c.get("nhom") != "hop_le":
            continue
        subs = await evaluate_criterion(c, artifact_content_map, max_page)
        agg = aggregate_subresults(c, subs)
        out.append({"criteria_ten": c["ten"], "result": agg["result"],
                    "score": agg["score"], "sub_results": subs})
    return out


def compute_completeness(
    criteria: list[dict[str, Any]], present_artifacts: set[str]
) -> dict[str, Any]:
    """Tính tỷ lệ hoàn thiện hồ sơ dựa trên artifact yêu cầu của các tiêu chí."""
    required: list[str] = []
    for c in criteria:
        for a in c.get("required_artifacts", []):
            if a not in required:
                required.append(a)
    missing = [a for a in required if a not in present_artifacts]
    percent = round(100.0 * (len(required) - len(missing)) / len(required), 1) if required else 100.0
    return {"percent": percent, "missing": missing, "required": required}
