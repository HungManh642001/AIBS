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
SYS_STRUCT = (
    "Bạn là chuyên gia đấu thầu. Với MỘT tiêu chí, phân rã thành sub_checks (ten, check_type, "
    "thong_so, required_artifact, blocking). Điền thong_so KHI NGUỒN có sẵn số. Với sub_check cần "
    "một con số/ngưỡng mà NGUỒN KHÔNG nêu rõ (thường trỏ sang BDS/HSMT), đặt "
    "thong_so._need = mô tả NGẮN giá trị còn thiếu (vd '_need':'giá trị bảo đảm dự thầu (đồng)'). "
    "TUYỆT ĐỐI KHÔNG bịa số — thiếu thì để _need, đừng đoán."
)
SYS_QUERY = (
    "Bạn tạo câu truy vấn tìm kiếm. Cho danh sách THÔNG TIN CÒN THIẾU của một tiêu chí, mỗi mục "
    "sinh 1 câu truy vấn tiếng Việt NGẮN, giàu từ khoá để tra trong HSMT/Bảng dữ liệu (BDS). "
    'Trả đúng dạng {"queries":[{"ten","query"}]} — ten khớp tên sub_check.'
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho tiêu chí đã phân rã (có sub_check còn thiếu số, đánh dấu "
    "thong_so._need) và PHẦN BẰNG CHỨNG truy hồi, hãy ĐIỀN thong_so cho các sub_check còn thiếu "
    "DỰA TRÊN bằng chứng rồi BỎ khoá _need. Nếu bằng chứng không có/không chắc, đặt "
    "thong_so.can_review=true và BỎ _need. TUYỆT ĐỐI KHÔNG bịa số."
)

_DETAIL_SCHEMA = (
    '{"nhom","ten","yeu_cau","required_artifacts":[...],"kieu","trong_so",'
    '"sub_checks":[{"ten","check_type","thong_so","required_artifact","blocking"}],'
    '"proposed_artifacts":[]}'
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


def struct_prompt(crit: dict[str, Any], source_text: str) -> str:
    """Bước 3a — phân rã cấu trúc; đánh dấu thong_so._need cho số còn thiếu."""
    return (
        f"[TAG:STRUCT:{crit.get('ten', '')}]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n\n"
        f"NGUỒN TCĐG:\n{source_text}\n\n"
        "Với mỗi sub_check cần số/ngưỡng mà NGUỒN không nêu rõ, đặt thong_so._need='<mô tả>'.\n\n"
        + cot_block(_DETAIL_SCHEMA, scale=SCALE_DEF)
    )


def query_prompt(crit: dict[str, Any], needs: list[dict[str, Any]]) -> str:
    """Bước 3b — sinh sub-query cho từng thông tin còn thiếu."""
    rows = "\n".join(
        f"- {sc.get('ten', '')}: {sc.get('thong_so', {}).get('_need', '')}" for sc in needs
    )
    return (
        f"[TAG:QUERY:{crit.get('ten', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n\n"
        f"THÔNG TIN CÒN THIẾU (ten sub_check: mô tả):\n{rows}\n\n"
        + cot_block('{"queries":[{"ten","query"}]}')
    )


def resolve_prompt(crit_item: dict[str, Any], evidence_text: str) -> str:
    """Bước 3c — điền số từ bằng chứng, bỏ _need; không thấy -> can_review."""
    import json as _json

    return (
        f"[TAG:RESOLVE:{crit_item.get('ten', '')}]\n"
        f"TIÊU CHÍ ĐÃ PHÂN RÃ (JSON):\n{_json.dumps(crit_item, ensure_ascii=False)}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/BDS):\n{evidence_text or '(không có)'}\n\n"
        + cot_block(_DETAIL_SCHEMA, scale=SCALE_DEF)
    )
