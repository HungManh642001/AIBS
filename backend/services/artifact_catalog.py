"""Danh mục loại hồ sơ (artifact) chuẩn theo Luật 22/2023 & NĐ 24/2024."""
from __future__ import annotations

CATALOG: dict[str, dict] = {
    "don_du_thau": {
        "label": "Đơn dự thầu", "nhom": "hop_le",
        "mo_ta": "Đơn dự thầu theo mẫu, có chữ ký và đóng dấu hợp lệ.",
        "aliases": ["đơn dự thầu", "don du thau", "mẫu số 01", "đơn xin dự thầu"],
    },
    "bao_dam_du_thau": {
        "label": "Bảo đảm dự thầu", "nhom": "hop_le",
        "mo_ta": "Thư bảo lãnh ngân hàng hoặc đặt cọc bảo đảm dự thầu.",
        "aliases": ["bảo đảm dự thầu", "bao dam du thau", "thư bảo lãnh", "thu bao lanh", "bảo lãnh dự thầu"],
    },
    "thoa_thuan_lien_danh": {
        "label": "Thỏa thuận liên danh", "nhom": "hop_le",
        "mo_ta": "Thỏa thuận liên danh nếu nhà thầu dự thầu theo hình thức liên danh.",
        "aliases": ["thỏa thuận liên danh", "thoa thuan lien danh", "liên danh"],
    },
    "tu_cach_phap_ly": {
        "label": "Tài liệu tư cách hợp lệ", "nhom": "hop_le",
        "mo_ta": "Giấy chứng nhận đăng ký doanh nghiệp, tư cách pháp lý.",
        "aliases": ["đăng ký doanh nghiệp", "dkkd", "tư cách hợp lệ", "tư cách pháp lý", "giấy chứng nhận đăng ký"],
    },
    "bao_cao_tai_chinh": {
        "label": "Báo cáo tài chính", "nhom": "nang_luc",
        "mo_ta": "Báo cáo tài chính các năm gần nhất.", "aliases": ["báo cáo tài chính", "bctc", "bao cao tai chinh"],
    },
    "hop_dong_tuong_tu": {
        "label": "Hợp đồng tương tự", "nhom": "nang_luc",
        "mo_ta": "Danh sách và chứng minh hợp đồng tương tự.", "aliases": ["hợp đồng tương tự", "hop dong tuong tu"],
    },
    "ke_khai_nhan_su": {
        "label": "Kê khai nhân sự", "nhom": "nang_luc",
        "mo_ta": "Nhân sự chủ chốt, CV, chứng chỉ.", "aliases": ["nhân sự chủ chốt", "ke khai nhan su", "cv nhân sự"],
    },
    "ke_khai_thiet_bi": {
        "label": "Kê khai thiết bị", "nhom": "nang_luc",
        "mo_ta": "Thiết bị, máy móc huy động.", "aliases": ["kê khai thiết bị", "thiết bị máy móc", "ke khai thiet bi"],
    },
    "de_xuat_ky_thuat": {
        "label": "Đề xuất kỹ thuật", "nhom": "ky_thuat",
        "mo_ta": "Thuyết minh giải pháp kỹ thuật.", "aliases": ["đề xuất kỹ thuật", "de xuat ky thuat", "giải pháp kỹ thuật"],
    },
    "catalogue_thong_so": {
        "label": "Catalogue / Bảng thông số", "nhom": "ky_thuat",
        "mo_ta": "Catalogue, bảng thông số kỹ thuật hàng hóa.", "aliases": ["catalogue", "thông số kỹ thuật", "bảng thông số"],
    },
    "bang_gia": {
        "label": "Bảng giá dự thầu", "nhom": "tai_chinh",
        "mo_ta": "Bảng chào giá chi tiết.", "aliases": ["bảng giá", "bang gia", "biểu giá", "chào giá"],
    },
}


def get_artifact(code: str) -> dict | None:
    """Lấy thông tin artifact theo code."""
    return CATALOG.get(code)


def all_codes() -> list[str]:
    """Trả danh sách tất cả mã artifact."""
    return list(CATALOG.keys())


def match_artifact(text: str) -> tuple[str | None, float]:
    """Trả (code, confidence) — code có nhiều alias khớp nhất trong text."""
    low = text.lower()
    best_code: str | None = None
    best_conf = 0.0
    for code, info in CATALOG.items():
        aliases = info["aliases"]
        hits = sum(1 for a in aliases if a.lower() in low)
        if hits == 0:
            continue
        conf = hits / len(aliases)
        if conf > best_conf:
            best_conf, best_code = conf, code
    return best_code, best_conf
