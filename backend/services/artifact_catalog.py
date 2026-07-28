"""Danh mục loại hồ sơ (artifact) chuẩn theo Luật 22/2023 & NĐ 24/2024."""
from __future__ import annotations

import re
import unicodedata

CATALOG: dict[str, dict] = {
    "don_du_thau": {
        "label": "Đơn dự thầu", "nhom": "hop_le",
        "mo_ta": "Đơn dự thầu, chứa nội dung tư cách hợp lệ.",
        "aliases": ["đơn dự thầu", "don du thau", "mẫu số 01", "đơn xin dự thầu"],
    },
    "bao_dam_du_thau": {
        "label": "Bảo đảm dự thầu", "nhom": "hop_le",
        "mo_ta": "Thư bảo lãnh ngân hàng hoặc Bảo đảm dự thầu.",
        "aliases": ["bảo đảm dự thầu", "bao dam du thau", "thư bảo lãnh", "thu bao lanh", "bảo lãnh dự thầu"],
    },
    "thoa_thuan_lien_danh": {
        "label": "Thỏa thuận liên danh", "nhom": "hop_le",
        "mo_ta": "Thỏa thuận liên danh nếu nhà thầu dự thầu theo hình thức liên danh.",
        "aliases": ["thỏa thuận liên danh", "thoa thuan lien danh", "liên danh"],
    },
    "dang_ky_kinh_doanh": {
        "label": "Giấy đăng ký kinh doanh", "nhom": "hop_le",
        "mo_ta": "Giấy chứng nhận đăng ký doanh nghiệp / đăng ký kinh doanh.",
        "aliases": ["đăng ký kinh doanh", "dang ky kinh doanh", "đăng ký doanh nghiệp", "dkkd",
                    "giấy chứng nhận đăng ký"],
    },
    "giay_uy_quyen": {
        "label": "Giấy ủy quyền", "nhom": "hop_le",
        "mo_ta": "Giấy ủy quyền của đại diện pháp luật cho người ký thay hồ sơ dự thầu.",
        "aliases": ["giấy ủy quyền", "giay uy quyen", "văn bản ủy quyền", "van ban uy quyen", "ủy quyền"],
    },
    "bao_cao_tai_chinh": {
        "label": "Báo cáo tài chính", "nhom": "nang_luc",
        "mo_ta": "Báo cáo tài chính.", "aliases": ["báo cáo tài chính", "bctc", "bao cao tai chinh"],
    },
    "hop_dong_tuong_tu": {
        "label": "Hợp đồng tương tự", "nhom": "nang_luc",
        "mo_ta": "Danh sách và chứng minh hợp đồng tương tự.", "aliases": ["hợp đồng tương tự", "hop dong tuong tu"],
    },
    "ke_khai_nhan_su": {
        "label": "Kê khai nhân sự", "nhom": "nang_luc",
        "mo_ta": "Kê khai nhân sự chủ chốt.", "aliases": ["nhân sự chủ chốt", "ke khai nhan su", "cv nhân sự"],
    },
    "ke_khai_thiet_bi": {
        "label": "Kê khai thiết bị", "nhom": "nang_luc",
        "mo_ta": "Kê khai thiết bị, máy móc huy động.", "aliases": ["kê khai thiết bị", "thiết bị máy móc", "ke khai thiet bi"],
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
        "mo_ta": "Bảng chào giá chi tiết, Bảng giá dự thầu.", "aliases": ["bảng giá", "bang gia", "biểu giá", "chào giá"],
    },
    "webform": {
        "label": "Webform / Kết quả mở thầu", "nhom": "tai_chinh",
        "mo_ta": "Webform / Kết quả mở thầu trên hệ thống — giá dự thầu của MỌI nhà thầu (dùng chung cả gói).",
        "aliases": ["webform", "web form", "kết quả mở thầu", "biên bản mở thầu",
                    "ket qua mo thau", "danh sách nhà thầu tham dự"],
        "dung_chung": True,
    },
}


def get_artifact(code: str) -> dict | None:
    """Lấy thông tin artifact theo code."""
    return CATALOG.get(code)


def all_codes() -> list[str]:
    """Trả danh sách tất cả mã artifact."""
    return list(CATALOG.keys())


def la_dung_chung(code: str) -> bool:
    """Tài liệu DÙNG CHUNG cả gói (chứa dữ liệu MỌI nhà thầu, vd webform)?

    Bước chấm PHẢI lọc về đúng nhà thầu đang chấm trước khi đưa vào prompt — nếu không, AI đọc
    nhầm dòng nhà thầu khác, và tài liệu dài còn làm trần ký tự cắt mất dòng cần đọc.
    """
    return bool((CATALOG.get(code) or {}).get("dung_chung", False))


def _norm_code(s: str) -> str:
    """Chuẩn hóa để so khớp mã: thường, bỏ dấu, đ->d, bỏ mọi ký tự không phải chữ/số."""
    s = (s or "").lower().strip().replace("đ", "d")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


_NORM_INDEX: dict[str, str] | None = None


def _norm_index() -> dict[str, str]:
    """Bảng tra: khoá chuẩn hóa (từ code + alias + label) -> code chuẩn trong danh mục."""
    global _NORM_INDEX
    if _NORM_INDEX is None:
        idx: dict[str, str] = {}
        for code, info in CATALOG.items():
            keys = {_norm_code(code), _norm_code(info["label"])}
            keys |= {_norm_code(a) for a in info["aliases"]}
            for k in keys:
                if k:
                    idx.setdefault(k, code)
        _NORM_INDEX = idx
    return _NORM_INDEX


def resolve_code(raw: str) -> str | None:
    """Ép 1 mã loại hồ sơ (LLM sinh) về code chuẩn trong danh mục.

    Khớp theo code/alias/label sau khi bỏ dấu và ký tự phân cách (vd 'bao_lanh_du_thau' ->
    'bao_dam_du_thau' qua alias 'bảo lãnh dự thầu'). Không khớp -> None (KHÔNG bịa).
    """
    nr = _norm_code(raw)
    if not nr:
        return None
    idx = _norm_index()
    if nr in idx:
        return idx[nr]
    for k, code in idx.items():  # mã dài/ngắn chứa nhau (vd chứa tiền tố)
        if k in nr or nr in k:
            return code
    return None


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
