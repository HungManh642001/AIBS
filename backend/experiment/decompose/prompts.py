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
    "hsdt_can_kiem_tra), hãy xác định CHECKLIST noi_dung_can_kiem_tra — những nội dung cần kiểm tra "
    "trên (các) hồ sơ hsdt_can_kiem_tra để kết luận tiêu chí. Liệt kê ĐẦY ĐỦ, đừng bỏ sót. Mỗi nội "
    "dung gồm:\n"
    "- noi_dung: điều cần kiểm trên HSDT (vd 'Giá trị bảo lãnh', 'Chữ ký & đóng dấu', 'Thời điểm ký đơn').\n"
    "- yeu_cau: CHUẨN của HSMT để đối chiếu — số/điều kiện (vd '≥ 90 ngày', 'phải có chữ ký', 'sau "
    "thời điểm phát hành HSMT'). Nếu chuẩn này là GIÁ TRỊ do HSMT quy định ở CHỖ KHÁC (E-BDL/E-CDNT; "
    "yeu_cau_goc chỉ trỏ tới chứ chưa nêu số) thì ĐỂ TRỐNG yeu_cau và đặt can_tra_cuu=true.\n"
    "- can_tra_cuu: true nếu yeu_cau cần TRA CỨU bổ sung từ HSMT; false nếu đã đủ/không cần số.\n"
    "- kieu_check: tồn tại | đối chiếu | so sánh ngày | định dạng | ...\n"
    "CHỈ tra cứu phía HSMT — TUYỆT ĐỐI KHÔNG bịa số; chưa có thì để trống yeu_cau + can_tra_cuu=true. "
    "Cũng đặt tien_quyet=true nếu là tiêu chí loại/cổng."
)
SYS_QUERY = (
    "Bạn tạo MỘT câu truy vấn tìm kiếm tiếng Việt NGẮN, giàu từ khoá để tra GIÁ TRỊ mà HSMT quy định "
    'cho MỘT nội dung (thường nằm trong E-BDL / E-CDNT). Trả đúng dạng {"query":"..."}.'
)
SYS_RESOLVE = (
    "Bạn là chuyên gia đấu thầu. Cho MỘT nội dung cần xác định giá trị và PHẦN BẰNG CHỨNG truy hồi từ "
    'HSMT, hãy trích GIÁ TRỊ/chuẩn tương ứng. Trả {"yeu_cau":"<giá trị>","can_review":false}. Nếu bằng '
    'chứng KHÔNG chứa/không chắc, trả {"yeu_cau":"","can_review":true} — TUYỆT ĐỐI KHÔNG bịa.'
)

# Schema step structure — noi_dung_can_kiem_tra là ô hạng nhất.
_CRIT_SCHEMA = (
    '{"nhom","ten","yeu_cau_goc","hsdt_can_kiem_tra":[...],"tien_quyet":false,'
    '"noi_dung_can_kiem_tra":[{"noi_dung","yeu_cau","can_tra_cuu":false,"kieu_check"}]}'
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
        "VÍ DỤ noi_dung_can_kiem_tra cho tiêu chí về bảo đảm dự thầu:\n"
        '  [{"noi_dung":"Giá trị bảo lãnh","yeu_cau":"","can_tra_cuu":true,"kieu_check":"đối chiếu"},\n'
        '   {"noi_dung":"Thời gian hiệu lực","yeu_cau":"","can_tra_cuu":true,"kieu_check":"đối chiếu"},\n'
        '   {"noi_dung":"Đơn vị thụ hưởng","yeu_cau":"","can_tra_cuu":true,"kieu_check":"đối chiếu"},\n'
        '   {"noi_dung":"Chữ ký & đóng dấu","yeu_cau":"phải có chữ ký hợp lệ","can_tra_cuu":false,"kieu_check":"tồn tại"}]\n\n'
        + cot_block(_CRIT_SCHEMA)
    )


def query_prompt(crit: dict[str, Any], need: dict[str, Any]) -> str:
    """Step search — sinh 1 truy vấn cho MỘT nội dung cần tra cứu."""
    return (
        f"[TAG:QUERY:{need.get('noi_dung', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"NỘI DUNG CẦN TRA GIÁ TRỊ (do HSMT quy định): {need.get('noi_dung', '')}\n\n"
        + cot_block('{"query":"..."}')
    )


def resolve_prompt(crit: dict[str, Any], need: dict[str, Any], evidence_text: str) -> str:
    """Step search — trích giá trị cho MỘT nội dung từ bằng chứng RIÊNG của nó; không thấy -> can_review."""
    return (
        f"[TAG:RESOLVE:{need.get('noi_dung', '')}]\n"
        f"TIÊU CHÍ: {crit.get('ten')}\n"
        f"NỘI DUNG: {need.get('noi_dung', '')}\n\n"
        f"BẰNG CHỨNG (truy hồi từ HSMT/E-BDL/E-CDNT):\n{evidence_text or '(không có)'}\n\n"
        + cot_block('{"yeu_cau":"<giá trị tìm được>","can_review":false}')
    )
