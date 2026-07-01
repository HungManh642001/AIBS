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
    "MỘT nhóm và LIỆT KÊ ĐẦY ĐỦ các tiêu chí cụ thể (đừng bỏ sót). "
    "QUY TẮC NGUYÊN TỬ — bắt buộc: mỗi tiêu chí chỉ hướng tới kiểm tra MỘT loại hồ sơ dự thầu ứng "
    "với MỘT nội dung. Nếu một loại hồ sơ có NHIỀU nội dung kiểm tra độc lập → TÁCH thành nhiều tiêu "
    "chí; KHÔNG gộp nhiều vấn đề vào một tiêu chí; KHÔNG để hai tiêu chí trùng/đè nội dung nhau. "
    "Mỗi tiêu chí: nhom (hop_le/nang_luc/ky_thuat/tai_chinh), ten (nhãn NGẮN), yeu_cau_goc (trích "
    "NGUYÊN VĂN/NGẮN GỌN câu yêu cầu gốc trong HSMT), hsdt_can_kiem_tra (loại hồ sơ HSDT cần xem)."
)
SYS_CRITIQUE = (
    "Bạn là chuyên gia rà soát. So sánh DANH SÁCH tiêu chí đã liệt kê với NGUỒN gốc và chỉ ra các "
    "tiêu chí BỊ SÓT (chỉ trả tiêu chí còn THIẾU, không lặp lại tiêu chí đã có). Giữ QUY TẮC NGUYÊN "
    "TỬ: mỗi tiêu chí = 1 loại hồ sơ + 1 nội dung. Mục tiêu: không sót."
)
SYS_STRUCT = (
    "Bạn là chuyên gia đấu thầu. Cho MỘT tiêu chí (đã có yeu_cau_goc trích từ HSMT và "
    "hsdt_can_kiem_tra), hãy lập CHECKLIST noi_dung_can_kiem_tra — những nội dung cần kiểm tra trên "
    "HSDT để kết luận tiêu chí. Liệt kê ĐẦY ĐỦ, đừng bỏ sót. Mỗi nội dung gồm:\n"
    "- noi_dung_kiem_tra: điều cần kiểm trên HSDT (vd 'Giá trị bảo lãnh', 'Bảo đảm tư cách hợp lệ').\n"
    "- hsdt_kiem_tra: CHỌN 1 loại hồ sơ HSDT (trong hsdt_can_kiem_tra của tiêu chí) để kiểm nội dung này.\n"
    "- yeu_cau: YÊU CẦU nội dung này phải đáp ứng, diễn theo yeu_cau_goc (vd 'Phải bảo đảm tư cách hợp "
    "lệ theo Mục 5 E-CDNT', 'Thỏa mãn giá trị bảo lãnh theo HSMT'). LUÔN điền.\n"
    "- can_lam_ro: nếu yeu_cau còn CHƯA RÕ (trỏ tới điều khoản/BDS mà chưa nêu con số/nội dung cụ thể) "
    "-> ghi NGẮN thứ cần làm rõ (vd 'Giá trị bảo lãnh', 'Nội dung tư cách hợp lệ tại Mục 5 E-CDNT'). "
    "Nếu đã rõ (không cần tra) -> để trống.\n"
    "- can_tra_cuu: true nếu can_lam_ro khác rỗng; false nếu không.\n"
    "- kieu_check: đối chiếu | tồn tại | so sánh ngày | ...\n"
    "TUYỆT ĐỐI KHÔNG bịa số/nội dung. Đặt tien_quyet=true nếu là tiêu chí loại/cổng."
)
SYS_QUERY = (
    "Bạn tạo MỘT câu truy vấn tìm kiếm tiếng Việt NGẮN, giàu từ khoá để tra trong HSMT (E-BDL / "
    "E-CDNT) phần THÔNG TIN CẦN LÀM RÕ cho một nội dung kiểm tra.\n"
    "QUAN TRỌNG — MỞ RỘNG THEO NGHIỆP VỤ: thông tin có thể được HSMT ghi dưới MỘT KHÁI NIỆM KHÁC; "
    "hãy THÊM từ đồng nghĩa / nơi thông tin thường nằm. Ví dụ: 'đơn vị thụ hưởng (của) bảo đảm dự "
    "thầu' THƯỜNG CHÍNH LÀ 'Chủ đầu tư / Bên mời thầu'. Query gồm CẢ từ gốc LẪN từ đồng nghĩa.\n"
    'Trả đúng dạng {"query":"..."}.'
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho THÔNG TIN CẦN LÀM RÕ của một nội dung và PHẦN BẰNG CHỨNG truy "
    "hồi từ HSMT, hãy trả 'thong_tin_bo_sung' — chuẩn cụ thể để bước chấm thầu đối chiếu:\n"
    "- TỰ ĐỦ: nếu bằng chứng trỏ tới nội dung điều khoản (vd tư cách hợp lệ Mục 5), TRÍCH NỘI DUNG "
    "THỰC (các điều kiện a, b, c...), KHÔNG trả lại con trỏ 'nội dung Mục 5'.\n"
    "- CÓ QUAN HỆ SO SÁNH: vd 'Giá trị bảo lãnh: 6.100.000 VNĐ', 'Thời gian hiệu lực: ≥ 120 ngày', "
    "'Đơn vị thụ hưởng: Liên doanh Việt - Nga Vietsovpetro', 'Đáp ứng đủ điều kiện: (a)...(b)...'.\n"
    "- 'nguon': mã điều khoản chứa thông tin (vd 'E-BDL 18.2', 'E-CDNT 1.1') trích từ bằng chứng.\n"
    'Trả {"thong_tin_bo_sung":"...","nguon":"...","can_review":false}. Nếu bằng chứng KHÔNG chứa/không '
    'chắc -> {"thong_tin_bo_sung":"","nguon":"","can_review":true} — TUYỆT ĐỐI KHÔNG bịa.'
)

# Schema step structure — noi_dung_can_kiem_tra là ô hạng nhất.
_CRIT_SCHEMA = (
    '{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...],"tien_quyet":false,'
    '"noi_dung_can_kiem_tra":[{"noi_dung_kiem_tra","hsdt_kiem_tra","yeu_cau","can_lam_ro",'
    '"can_tra_cuu":false,"kieu_check"}]}'
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
        + cot_block('{"criteria":[{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...]}]}')
    )


def critique_prompt(source_text: str, listed: list[dict[str, Any]]) -> str:
    names = "; ".join(c.get("ten", "") for c in listed)
    return (
        "[TAG:CRITIQUE]\n"
        f"NGUỒN:\n{source_text}\n\n"
        f"ĐÃ LIỆT KÊ: {names}\n\n"
        + cot_block('{"criteria":[{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...]}]}  // CHỈ tiêu chí còn thiếu')
    )


def struct_prompt(crit: dict[str, Any]) -> str:
    """Step analyze — chỉ từ tiêu chí (KHÔNG đưa source toàn nhóm để tránh nhiễu)."""
    return (
        f"[TAG:STRUCT:{crit.get('ten', '')}]\n"
        f"Danh mục loại hồ sơ (code=label): {catalog_codes()}\n\n"
        f"TIÊU CHÍ: {crit.get('ten')} (nhóm {crit.get('nhom', 'hop_le')})\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"HSDT cần kiểm tra: {crit.get('hsdt_can_kiem_tra', [])}\n\n"
        "VÍ DỤ 1 — 'Nhà thầu bảo đảm tư cách hợp lệ theo Mục 5 E-CDNT' (hsdt=[don_du_thau]):\n"
        '  [{"noi_dung_kiem_tra":"Bảo đảm tư cách hợp lệ","hsdt_kiem_tra":"don_du_thau",'
        '"yeu_cau":"Phải bảo đảm tư cách hợp lệ theo Mục 5 E-CDNT",'
        '"can_lam_ro":"Nội dung tư cách hợp lệ tại Mục 5 E-CDNT","can_tra_cuu":true,"kieu_check":"đối chiếu"}]\n'
        "VÍ DỤ 2 — 'Thư bảo lãnh đúng giá trị/hiệu lực/đơn vị thụ hưởng theo HSMT' (hsdt=[bao_lanh_du_thau]):\n"
        '  [{"noi_dung_kiem_tra":"Giá trị bảo lãnh","hsdt_kiem_tra":"bao_lanh_du_thau",'
        '"yeu_cau":"Thỏa mãn giá trị bảo lãnh theo HSMT","can_lam_ro":"Giá trị bảo lãnh","can_tra_cuu":true,"kieu_check":"đối chiếu"},\n'
        '   {"noi_dung_kiem_tra":"Thời gian hiệu lực","hsdt_kiem_tra":"bao_lanh_du_thau",'
        '"yeu_cau":"Thỏa mãn thời gian hiệu lực theo HSMT","can_lam_ro":"Thời gian hiệu lực bảo lãnh","can_tra_cuu":true,"kieu_check":"đối chiếu"}]\n\n'
        + cot_block(_CRIT_SCHEMA)
    )


def query_prompt(crit: dict[str, Any], need: dict[str, Any]) -> str:
    """Step search — sinh 1 truy vấn cho THÔNG TIN CẦN LÀM RÕ của một nội dung (kèm ngữ cảnh)."""
    return (
        f"[TAG:QUERY:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU GỐC (HSMT): {crit.get('yeu_cau_goc', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ (tra trong HSMT): {need.get('can_lam_ro', '')}\n\n"
        + cot_block('{"query":"..."}')
    )


def resolve_prompt(crit: dict[str, Any], need: dict[str, Any], evidence_text: str) -> str:
    """Step search — trả thong_tin_bo_sung (tự đủ + quan hệ so sánh) + nguon; không thấy -> can_review."""
    return (
        f"[TAG:RESOLVE:{need.get('noi_dung_kiem_tra', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"YÊU CẦU: {need.get('yeu_cau', '')}\n"
        f"THÔNG TIN CẦN LÀM RÕ: {need.get('can_lam_ro', '')}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/E-BDL/E-CDNT):\n{evidence_text or '(không có)'}\n\n"
        + cot_block('{"thong_tin_bo_sung":"<chuẩn cụ thể, tự đủ, có quan hệ so sánh>","nguon":"<mã điều khoản>","can_review":false}')
    )
