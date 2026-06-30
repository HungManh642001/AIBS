"""System prompt + builder cho các bước phân rã. Dùng cot_block của services.

Mỗi prompt nhúng 1 TAG máy đọc được ([TAG:LIST]/[TAG:CRITIQUE]/[TAG:STRUCT:<ten>]/
[TAG:QUERY:<ten>]/[TAG:RESOLVE:<ten>]) để ScriptedLlm khớp kịch bản theo bước (bền với fan-out).

Output phẳng: mỗi tiêu chí có noi_dung_can_kiem_tra (ô HẠNG NHẤT) — buộc model liệt kê rõ
"cần kiểm tra nội dung gì", thay vì chôn trong thong_so.
"""
from __future__ import annotations

from typing import Any

from services import artifact_catalog
from services.prompts import cot_block

SYS_LIST = (
    "Bạn là chuyên gia đấu thầu theo Luật Đấu thầu Việt Nam. Đọc nội dung TIÊU CHUẨN ĐÁNH GIÁ của "
    "MỘT nhóm và LIỆT KÊ ĐẦY ĐỦ các tiêu chí (đừng bỏ sót). "
    "QUY TẮC NGUYÊN TỬ — bắt buộc: mỗi tiêu chí chỉ hướng tới kiểm tra MỘT loại hồ sơ dự thầu ứng "
    "với MỘT nội dung. Nếu một loại hồ sơ có NHIỀU nội dung kiểm tra độc lập → TÁCH thành nhiều tiêu "
    "chí; KHÔNG gộp nhiều vấn đề vào một tiêu chí; KHÔNG để hai tiêu chí trùng/đè nội dung nhau. "
    "Mỗi tiêu chí: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), ten (nhãn NGẮN), hsdt_can_kiem_tra "
    "(loại hồ sơ HSDT cần xem)."
)
SYS_CRITIQUE = (
    "Bạn là chuyên gia rà soát. So sánh DANH SÁCH tiêu chí đã liệt kê với NGUỒN gốc và chỉ ra các "
    "tiêu chí BỊ SÓT (chỉ trả tiêu chí còn THIẾU, không lặp lại tiêu chí đã có). Giữ QUY TẮC NGUYÊN "
    "TỬ: mỗi tiêu chí = 1 loại hồ sơ + 1 nội dung. Mục tiêu: không sót."
)
SYS_STRUCT = (
    "Bạn là chuyên gia đấu thầu. Với MỘT tiêu chí, xác định:\n"
    "1) yeu_cau_goc: trích NGẮN yêu cầu gốc từ NGUỒN.\n"
    "2) hsdt_can_kiem_tra: (các) loại hồ sơ HSDT cần xem để kiểm tra.\n"
    "3) tien_quyet: true nếu là tiêu chí loại/cổng (vi phạm là loại HSDT).\n"
    "4) noi_dung_can_kiem_tra — QUAN TRỌNG NHẤT: liệt kê ĐẦY ĐỦ từng NỘI DUNG cần kiểm tra trên "
    "HSDT, đừng bỏ sót. Mỗi nội dung gồm: ten; nguon; kieu_check; gia_tri. Trong đó:\n"
    "   • nguon='hsmt' nếu là GIÁ TRỊ/NGƯỠNG/MỐC do HSMT quy định để đối chiếu (vd: giá trị bảo "
    "lãnh, thời gian hiệu lực bảo lãnh, đơn vị thụ hưởng, số ngày hiệu lực HSDT, doanh thu yêu cầu). "
    "Nếu NGUỒN đã nêu rõ con số → điền vào gia_tri; nếu CHƯA có → ĐỂ TRỐNG gia_tri (bước sau tra bổ sung).\n"
    "   • nguon='hsdt' nếu là dữ liệu do NHÀ THẦU cung cấp (đánh giá sau, HIỆN CHƯA CÓ, vd: ngày ký "
    "đơn/thư bảo lãnh, giá dự thầu); gia_tri ghi điều kiện cần thỏa (vd 'sau thời điểm phát hành HSMT').\n"
    "   • kieu_check: nhãn nhẹ — tồn tại / đối chiếu / so sánh ngày / ...\n"
    "TUYỆT ĐỐI KHÔNG bịa số — chưa có thì để trống, đừng đoán."
)
SYS_QUERY = (
    "Bạn tạo câu truy vấn tìm kiếm. Cho danh sách NỘI DUNG cần tra giá trị (do HSMT quy định) của "
    "một tiêu chí, mỗi mục sinh 1 câu truy vấn tiếng Việt NGẮN, giàu từ khoá để tra trong HSMT / "
    'Bảng dữ liệu (E-BDL) / Chỉ dẫn nhà thầu (E-CDNT). Trả đúng dạng {"queries":[{"ten","query"}]} '
    "— ten khớp tên nội dung."
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho tiêu chí (kèm noi_dung_can_kiem_tra có mục nguon='hsmt' còn "
    "TRỐNG gia_tri) và PHẦN BẰNG CHỨNG truy hồi từ HSMT, hãy ĐIỀN gia_tri tìm được cho từng nội dung "
    "tương ứng. Với nội dung KHÔNG tìm thấy/không chắc trong bằng chứng, đặt can_review=true (để "
    "trống gia_tri). GIỮ NGUYÊN các trường khác. TUYỆT ĐỐI KHÔNG bịa số."
)

# Schema step structure/resolve — noi_dung_can_kiem_tra là ô hạng nhất.
_CRIT_SCHEMA = (
    '{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...],"tien_quyet":false,'
    '"noi_dung_can_kiem_tra":[{"ten","gia_tri","nguon":"hsmt|hsdt","kieu_check"}]}'
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
        + cot_block('{"criteria":[{"nhom","ten","hsdt_can_kiem_tra":[...]}]}')
    )


def critique_prompt(source_text: str, listed: list[dict[str, Any]]) -> str:
    names = "; ".join(c.get("ten", "") for c in listed)
    return (
        "[TAG:CRITIQUE]\n"
        f"NGUỒN:\n{source_text}\n\n"
        f"ĐÃ LIỆT KÊ: {names}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","hsdt_can_kiem_tra":[...]}]}  // CHỈ tiêu chí còn thiếu')
    )


def struct_prompt(crit: dict[str, Any], source_text: str) -> str:
    """Step structure — xác định yeu_cau_goc + noi_dung_can_kiem_tra (gia_tri để trống nếu chưa có)."""
    return (
        f"[TAG:STRUCT:{crit.get('ten', '')}]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n\n"
        f"NGUỒN TCĐG:\n{source_text}\n\n"
        "VÍ DỤ noi_dung_can_kiem_tra cho tiêu chí về bảo đảm dự thầu:\n"
        '  [{"ten":"Giá trị bảo lãnh","gia_tri":"","nguon":"hsmt","kieu_check":"đối chiếu"},\n'
        '   {"ten":"Thời gian hiệu lực","gia_tri":"","nguon":"hsmt","kieu_check":"đối chiếu"},\n'
        '   {"ten":"Đơn vị thụ hưởng","gia_tri":"","nguon":"hsmt","kieu_check":"đối chiếu"},\n'
        '   {"ten":"Ngày ký thư bảo lãnh","gia_tri":"sau thời điểm phát hành HSMT","nguon":"hsdt","kieu_check":"so sánh ngày"}]\n\n'
        + cot_block(_CRIT_SCHEMA)
    )


def query_prompt(crit: dict[str, Any], needs: list[dict[str, Any]]) -> str:
    """Step subquery — sinh truy vấn cho từng nội dung nguon=hsmt còn trống gia_tri."""
    rows = "\n".join(f"- {n.get('ten', '')}" for n in needs)
    return (
        f"[TAG:QUERY:{crit.get('ten', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n\n"
        f"CÁC NỘI DUNG CẦN TRA GIÁ TRỊ (do HSMT quy định):\n{rows}\n\n"
        + cot_block('{"queries":[{"ten","query"}]}')
    )


def resolve_prompt(crit_item: dict[str, Any], evidence_text: str) -> str:
    """Step resolve — điền gia_tri từ bằng chứng; không thấy -> can_review."""
    import json as _json

    return (
        f"[TAG:RESOLVE:{crit_item.get('ten', '')}]\n"
        f"TIÊU CHÍ (JSON, có noi_dung_can_kiem_tra còn trống gia_tri):\n"
        f"{_json.dumps(crit_item, ensure_ascii=False)}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/E-BDL/E-CDNT):\n{evidence_text or '(không có)'}\n\n"
        + cot_block(_CRIT_SCHEMA)
    )
