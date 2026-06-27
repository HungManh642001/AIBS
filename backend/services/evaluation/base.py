"""Kiểu dữ liệu & helper dùng chung cho các module đánh giá."""
from __future__ import annotations
from typing import Any, TypedDict

from services.ai_client import ai_call
from services.evaluation.checks import run_deterministic_check
from services import artifact_catalog
from services.json_utils import clamp_page_refs
from services.prompts import cot_block, SCALE_DEF
from services.ai_schemas import validate_eval_verdict, validate_sub_verdict


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
        + cot_block('{"evidence":"...","result":"PASS|FAIL|PARTIAL","score":0-100,"page_ref":[...],"note":"..."}',
                    scale=SCALE_DEF)
    )
    out = await ai_call(system, prompt, mock_key=mock_key, validate=validate_eval_verdict)
    if out.status == "error":
        return EvalResult(
            criteria_ten=criteria.get("ten", ""), result="ERROR", score=0.0,
            evidence=f"AI lỗi: {out.error}", page_ref=[], note="", ai_model="",
        )
    data = out.data
    result = data.get("result", "PARTIAL")
    if result not in {"PASS", "FAIL", "PARTIAL"}:
        result = "PARTIAL"
    return EvalResult(
        criteria_ten=criteria.get("ten", ""),
        result=result,
        score=_clamp(data.get("score", 0)),
        evidence=data.get("evidence") or "Không có dẫn chứng",
        page_ref=clamp_page_refs(data.get("page_ref"), 0),
        note=data.get("note", ""),
        ai_model=out.model,
    )


_SYS_SUB = "Bạn là chuyên gia đánh giá HSDT theo Luật Đấu thầu VN. Chỉ trả JSON."


class SubResult(TypedDict):
    sub_check_ten: str
    result: str
    evidence: str
    page_ref: list[int]
    nguon_file: str
    ai_model: str


def _label(code: str) -> str:
    """Trả nhãn hiển thị của artifact theo code, hoặc code nếu không tìm thấy."""
    a = artifact_catalog.get_artifact(code)
    return a["label"] if a else code


async def evaluate_criterion(
    criterion: dict[str, Any], artifact_content_map: dict[str, str], max_page: int = 0
) -> list[SubResult]:
    """Đánh giá từng sub_check của một tiêu chí, routing sang deterministic hoặc AI."""
    out: list[SubResult] = []
    valid_codes = set(artifact_catalog.all_codes())
    for sc in criterion.get("sub_checks", []):
        art = sc.get("required_artifact", "")
        if art and art not in valid_codes:
            # Mã hồ sơ AI đề xuất nằm ngoài danh mục -> cần người xử lý, KHÔNG đổ lỗi nhà thầu.
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="ERROR",
                evidence=f"AI đề xuất loại hồ sơ ngoài danh mục: {art}",
                page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        if not art or art not in artifact_content_map:
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="FAIL",
                evidence=f"Thiếu hồ sơ: {_label(art)}",
                page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        content = artifact_content_map[art]
        det = run_deterministic_check(sc.get("check_type", ""), content, sc.get("thong_so", {}))
        if det is not None:
            out.append(SubResult(
                sub_check_ten=sc["ten"], result=det["result"], evidence=det["evidence"],
                page_ref=det.get("page_ref") or [], nguon_file=art, ai_model="python",
            ))
            continue
        prompt = (
            f"Điểm kiểm: {sc['ten']} (loại {sc.get('check_type')})\n"
            f"Nội dung hồ sơ '{_label(art)}':\n{content[:6000]}\n\n"
            + cot_block('{"evidence":"...","result":"PASS|FAIL|PARTIAL","page_ref":[...]}', scale=SCALE_DEF)
        )
        res_out = await ai_call(_SYS_SUB, prompt, mock_key="eval_subcheck", validate=validate_sub_verdict)
        if res_out.status == "error":
            out.append(SubResult(
                sub_check_ten=sc["ten"], result="ERROR",
                evidence=f"AI lỗi: {res_out.error}", page_ref=[], nguon_file=art, ai_model="",
            ))
            continue
        data = res_out.data
        res = data.get("result", "PARTIAL")
        if res not in {"PASS", "FAIL", "PARTIAL"}:
            res = "PARTIAL"
        out.append(SubResult(
            sub_check_ten=sc["ten"], result=res,
            evidence=data.get("evidence") or "Không có dẫn chứng",
            page_ref=clamp_page_refs(data.get("page_ref"), max_page),
            nguon_file=art, ai_model=res_out.model,
        ))
    return out


def aggregate_subresults(criterion: dict[str, Any], sub_results: list[SubResult]) -> dict[str, Any]:
    """Tổng hợp kết quả sub_check thành verdict của tiêu chí."""
    by_ten = {sc["ten"]: sc for sc in criterion.get("sub_checks", [])}
    blocking_fail = any(
        r["result"] == "FAIL" and by_ten.get(r["sub_check_ten"], {}).get("blocking", True)
        for r in sub_results
    )
    error_present = any(r["result"] == "ERROR" for r in sub_results)
    all_pass = bool(sub_results) and all(r["result"] == "PASS" for r in sub_results)
    if error_present:
        result = "ERROR"
    elif blocking_fail:
        result = "FAIL"
    elif all_pass:
        result = "PASS"
    else:
        result = "PARTIAL"
    passed = sum(1 for r in sub_results if r["result"] == "PASS")
    score = round(100.0 * passed / len(sub_results), 1) if sub_results else 0.0
    return {"result": result, "score": score}
