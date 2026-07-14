"""System prompt + builder cho ingest (đọc ảnh) và evaluate (đối chiếu HSDT vs chuẩn HSMT)."""
from __future__ import annotations

from typing import Any

from services.prompts import cot_block

from experiment.evaluate.schema import HINH_THUC_DOC_LAP


SYS_INGEST = (
    "Bạn đọc ẢNH một trang hồ sơ dự thầu (HSDT) scan tiếng Việt. Hãy: (1) BÓC toàn bộ chữ thành text "
    "(giữ số/tên/ngày chính xác, KHÔNG bịa); (2) Nếu có chữ ký, con dấu hãy mô tả chi tiết; (3) ghi co_chu_ky (có chữ ký tay/scan không), co_dau "
    "(có con dấu đỏ/đóng dấu không). KHÔNG cần phân loại hồ sơ (loại đã biết khi tải). Chỉ trả JSON."
)


def ingest_prompt() -> str:
    return (
        "[IN]\n"
        + cot_block('{"text":"<toàn bộ chữ trong ảnh kèm mô tả bổ sung>","co_chu_ky":false,"co_dau":false}')
    )


SYS_VENDOR_FORM = (
    "Bạn là chuyên gia chấm thầu. Đọc ĐƠN DỰ THẦU và xác định nhà thầu dự thầu theo hình thức "
    "'độc lập' (một pháp nhân duy nhất đứng tên) hay 'liên danh' (nhiều thành viên cùng đứng tên, "
    "thường ghi 'liên danh A-B', 'thành viên đứng đầu liên danh', 'thay mặt liên danh'). "
    "hinh_thuc: 'độc lập' | 'liên danh' | '' nếu đơn KHÔNG nêu rõ — TUYỆT ĐỐI KHÔNG suy đoán từ "
    "việc đơn chỉ nhắc MỘT tên công ty. bang_chung: TRÍCH nguyên văn câu trong đơn làm căn cứ "
    "(KHÔNG bịa); trang: số trang chứa căn cứ; do_tin: 0-1, chỉ >= 0.7 khi đơn nêu RÕ RÀNG. "
    "Chỉ trả JSON."
)


def vendor_form_prompt(don_text: str, vendor: Any | None = None) -> str:
    ten = f"NHÀ THẦU ĐANG CHẤM: {vendor.ten}\n" if vendor is not None and vendor.ten else ""
    return (
        "[VENDOR_FORM]\n"
        f"{ten}"
        f"ĐƠN DỰ THẦU (bóc từ ảnh):\n{don_text}\n\n"
        + cot_block('{"hinh_thuc":"độc lập|liên danh|","bang_chung":"<trích nguyên văn từ đơn>",'
                    '"trang":[...],"do_tin":0.0,"ghi_chu":""}')
    )


SYS_EVAL = (
    "Bạn là chuyên gia chấm thầu. Đối chiếu NỘI DUNG HSDT của nhà thầu với CHUẨN của HSMT để kết "
    "luận. ket_qua: 'đạt' nếu HSDT thỏa mãn; 'không đạt' nếu vi phạm/không thỏa; 'cần làm rõ' nếu "
    "không đủ căn cứ. bang_chung: TRÍCH nguyên văn phần HSDT làm căn cứ (KHÔNG bịa); trang: số "
    "trang HSDT chứa căn cứ; do_tin: 0-1.\n"
    "- CHUẨN ghi '(không có)' mà YÊU CẦU trỏ tới giá trị/chuẩn trong HSMT -> KHÔNG kết luận "
    "đạt/không đạt, trả 'cần làm rõ' (thiếu căn cứ chuẩn).\n"
    "- CHUẨN chứa mốc ngày/giờ cụ thể -> đối chiếu mốc thời gian trong HSDT với mốc chuẩn "
    "(tính khoảng ngày khi là thời hạn/hiệu lực); bang_chung trích CẢ HAI mốc.\n"
    "- Nếu phần đầu prompt có dòng nêu nhà thầu dự thầu theo hình thức 'độc lập' VÀ yêu cầu NÊU RÕ "
    "chỉ áp dụng cho nhà thầu liên danh -> trả ket_qua='không áp dụng' và BẮT BUỘC ghi_chu nêu căn "
    "cứ (trích phần yêu cầu chỉ dành cho liên danh). Nếu KHÔNG có dòng đó -> TUYỆT ĐỐI KHÔNG dùng "
    "'không áp dụng'.\n"
    "Chỉ trả JSON."
)

_SCHEMA_EVAL = ('{"ket_qua":"đạt|không đạt|cần làm rõ","bang_chung":"<trích HSDT>","trang":[...],'
                '"do_tin":0.0,"ghi_chu":""}')
_SCHEMA_EVAL_NA = ('{"ket_qua":"đạt|không đạt|cần làm rõ|không áp dụng","bang_chung":"<trích HSDT>",'
                   '"trang":[...],"do_tin":0.0,"ghi_chu":""}')


def _vendor_block(vendor_ctx: Any | None, profile: Any | None) -> str:
    """Khối danh tính + hình thức dự thầu. Hình thức KHÔNG RÕ -> khối rỗng (AI không được suy đoán)."""
    if profile is None or not profile.hinh_thuc:
        return ""
    ten = vendor_ctx.ten if vendor_ctx is not None and vendor_ctx.ten else "(không nêu tên)"
    can_cu = f"căn cứ: {profile.nguon}"
    if profile.bang_chung:
        can_cu += f"; {profile.bang_chung}"
    return f"[NHÀ THẦU] {ten} — dự thầu theo hình thức: {profile.hinh_thuc} ({can_cu})\n"


def eval_prompt(nd_item: dict[str, Any], hsdt_text: str, cross: bool = False, *,
                vendor_ctx: Any | None = None, profile: Any | None = None) -> str:
    """cross (need doi_chieu_hsdt): text đã ghép NHIỀU loại hồ sơ (cap per-type) — đối chiếu chéo.

    profile: nêu hình thức dự thầu để AI xử lý đúng yêu cầu chỉ dành cho liên danh. Tùy chọn
    'không áp dụng' CHỈ mở khi code đã xác định nhà thầu ĐỘC LẬP (whitelist thật ở evaluate.py).
    """
    body_label = "NỘI DUNG HSDT (đã bóc từ ảnh, kèm mô tả chữ ký/đóng dấu nếu có)"
    if cross:
        body_label = ("CHUẨN nằm trong chính HSDT — ĐỐI CHIẾU CHÉO giữa các hồ sơ dưới đây\n"
                      "NỘI DUNG HSDT theo từng loại hồ sơ")
    body = hsdt_text if cross else hsdt_text[:6000]  # cross đã cap per-type
    mo_na = profile is not None and profile.hinh_thuc == HINH_THUC_DOC_LAP
    return (
        f"[EV:{nd_item.get('noi_dung_kiem_tra', '')}]\n"
        f"{_vendor_block(vendor_ctx, profile)}"
        f"NỘI DUNG KIỂM TRA: {nd_item.get('noi_dung_kiem_tra', '')}\n"
        f"YÊU CẦU (theo HSMT): {nd_item.get('yeu_cau', '')}\n"
        f"CHUẨN HSMT (thông tin bổ sung): {nd_item.get('thong_tin_bo_sung', '') or '(không có)'}\n\n"
        f"{body_label}:\n{body}\n\n"
        + cot_block(_SCHEMA_EVAL_NA if mo_na else _SCHEMA_EVAL)
    )
