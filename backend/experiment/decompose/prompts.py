"""System prompt + builder cho các bước phân rã. Dùng cot_block + SCALE_DEF của services.

Mỗi prompt nhúng 1 TAG máy đọc được ([TAG:LIST]/[TAG:CRITIQUE]/[TAG:DETAIL:<ten>]) để
ScriptedLlm khớp kịch bản theo bước (bền với fan-out song song).
"""
from __future__ import annotations

from typing import Any

from services import artifact_catalog
from services.prompts import SCALE_DEF, cot_block

SYS_LIST = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc nội dung TIÊU CHUẨN ĐÁNH GIÁ của "
    "MỘT nhóm và LIỆT KÊ ĐẦY ĐỦ các tiêu chí đánh giá nguyên tử (đừng bỏ sót). Mỗi tiêu chí gồm: "
    "nhom (hop_le/nang_luc/ky_thuat/tai_chinh), ten, required_artifacts (mã loại hồ sơ)."
)
SYS_CRITIQUE = (
    "Bạn là chuyên gia rà soát. So sánh DANH SÁCH tiêu chí đã liệt kê với NGUỒN gốc và chỉ ra các "
    "tiêu chí BỊ SÓT (chỉ trả tiêu chí còn THIẾU, không lặp lại tiêu chí đã có). Mục tiêu: không sót."
)
SYS_DETAIL = (
    "Bạn là chuyên gia đấu thầu. Với MỘT tiêu chí, bóc thành sub_checks kèm check_type và ngưỡng "
    "(thong_so). Khi cần số 'theo yêu cầu HSMT', dùng PHẦN BẰNG CHỨNG cho sẵn; nếu không có/không "
    "chắc, đặt thong_so.can_review=true — TUYỆT ĐỐI KHÔNG bịa số."
)


def catalog_codes() -> str:
    return ", ".join(
        f"{c}={artifact_catalog.get_artifact(c)['label']}" for c in artifact_catalog.all_codes()
    )


def list_prompt(source_text: str) -> str:
    return (
        "[TAG:LIST]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        f"NỘI DUNG TIÊU CHUẨN ĐÁNH GIÁ (nhóm):\n{source_text}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","required_artifacts":[...]}]}')
    )


def critique_prompt(source_text: str, listed: list[dict[str, Any]]) -> str:
    names = "; ".join(c.get("ten", "") for c in listed)
    return (
        "[TAG:CRITIQUE]\n"
        f"NGUỒN:\n{source_text}\n\n"
        f"ĐÃ LIỆT KÊ: {names}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","required_artifacts":[...]}]}  // CHỈ tiêu chí còn thiếu')
    )


def detail_prompt(crit: dict[str, Any], source_text: str, evidence_text: str) -> str:
    return (
        f"[TAG:DETAIL:{crit.get('ten', '')}]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n\n"
        f"NGUỒN TCĐG:\n{source_text}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/BDS):\n{evidence_text or '(không có)'}\n\n"
        + cot_block(
            '{"nhom","ten","yeu_cau","required_artifacts":[...],"kieu","trong_so",'
            '"sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
            '"proposed_artifacts":[]}',
            scale=SCALE_DEF,
        )
    )
