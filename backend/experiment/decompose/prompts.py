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
    "MỘT nhóm và LIỆT KÊ ĐẦY ĐỦ các tiêu chí (đừng bỏ sót). "
    "QUY TẮC NGUYÊN TỬ — bắt buộc: mỗi tiêu chí chỉ hướng tới ĐÁNH GIÁ MỘT loại hồ sơ dự thầu "
    "(required_artifacts = ĐÚNG 1 mã loại hồ sơ chính) ứng với MỘT nội dung cần kiểm tra. Nếu một "
    "loại hồ sơ có NHIỀU nội dung kiểm tra độc lập → TÁCH thành nhiều tiêu chí riêng. KHÔNG gộp "
    "nhiều vấn đề vào một tiêu chí; KHÔNG để hai tiêu chí trùng/đè nội dung nhau. "
    "Mỗi tiêu chí gồm: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), ten (ngắn, nêu RÕ nội dung kiểm), "
    "required_artifacts (1 mã loại hồ sơ)."
)
SYS_CRITIQUE = (
    "Bạn là chuyên gia rà soát. So sánh DANH SÁCH tiêu chí đã liệt kê với NGUỒN gốc và chỉ ra các "
    "tiêu chí BỊ SÓT (chỉ trả tiêu chí còn THIẾU, không lặp lại tiêu chí đã có). Giữ QUY TẮC NGUYÊN "
    "TỬ: mỗi tiêu chí = 1 loại hồ sơ + 1 nội dung kiểm; tách nếu cần. Mục tiêu: không sót."
)
SYS_STRUCT = (
    "Bạn là chuyên gia đấu thầu. Với MỘT tiêu chí, phân rã thành sub_checks (ten, check_type, "
    "thong_so, required_artifact, blocking). Điền thong_so KHI NGUỒN có sẵn số.\n"
    "PHÂN BIỆT NGUỒN GIÁ TRỊ khi đánh dấu thiếu:\n"
    "(a) Giá trị THAM CHIẾU do HSMT quy định — mốc/ngưỡng/giá trị chuẩn để đối chiếu (vd thời điểm "
    "phát hành HSMT, giá trị & số ngày hiệu lực bảo đảm dự thầu tối thiểu, doanh thu yêu cầu). Nếu "
    "NGUỒN không nêu rõ -> đặt thong_so._need='<mô tả>' và thong_so._need_source='hsmt' (sẽ truy hồi "
    "bổ sung từ HSMT/BDS).\n"
    "(b) Dữ liệu do NHÀ THẦU nộp trong HSDT — thứ sẽ ĐÁNH GIÁ Ở BƯỚC SAU, HIỆN CHƯA CÓ (vd thời gian "
    "ký đơn dự thầu, giá dự thầu, số liệu năng lực thực tế của nhà thầu). TUYỆT ĐỐI KHÔNG coi là "
    "thiếu, KHÔNG đặt _need cho nó; chỉ đặt thong_so._danh_gia_sau=true để bước đánh giá sau lấy từ HSDT.\n"
    "VÍ DỤ — tiêu chí 'thời gian ký đơn dự thầu phải SAU thời điểm phát hành HSMT': chỉ THIẾU 'thời "
    "điểm phát hành HSMT' (_need + _need_source='hsmt'); còn 'thời gian ký đơn dự thầu' là dữ liệu "
    "HSDT (_danh_gia_sau=true), KHÔNG phải thiếu.\n"
    "TUYỆT ĐỐI KHÔNG bịa số — thiếu (phía HSMT) thì để _need, đừng đoán."
)
SYS_QUERY = (
    "Bạn tạo câu truy vấn tìm kiếm. Cho danh sách THÔNG TIN CÒN THIẾU của một tiêu chí, mỗi mục "
    "sinh 1 câu truy vấn tiếng Việt NGẮN, giàu từ khoá để tra trong HSMT/Bảng dữ liệu (BDS). "
    'Trả đúng dạng {"queries":[{"ten","query"}]} — ten khớp tên sub_check.'
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho tiêu chí đã phân rã (có sub_check còn thiếu số phía HSMT, đánh "
    "dấu thong_so._need) và PHẦN BẰNG CHỨNG truy hồi, hãy ĐIỀN thong_so cho các sub_check còn thiếu "
    "DỰA TRÊN bằng chứng rồi BỎ khoá _need. Nếu bằng chứng không có/không chắc, đặt "
    "thong_so.can_review=true và BỎ _need. GIỮ NGUYÊN các khoá thong_so khác (kể cả _danh_gia_sau). "
    "TUYỆT ĐỐI KHÔNG bịa số."
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
