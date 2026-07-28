"""Đối chiếu ĐIỀU KIỆN ÁP DỤNG theo giá trị — TẤT ĐỊNH, 0 call LLM.

Bài toán: HSMT có tiêu chí chỉ áp dụng khi một đại lượng của GÓI THẦU thoả điều kiện, vd "Đối với
gói thầu có giá trị bảo đảm dự thầu nhỏ hơn 50 triệu đồng, nhà thầu có cam kết trong đơn dự thầu
theo Mục 17.8 A-CDNT". Gói này quy định 939.000.000 VND nên nội dung đó KHÔNG cần chấm — nhưng
trước đây điều kiện chỉ nằm dưới dạng văn xuôi trong `yeu_cau` nên không ai đọc, và nội dung luôn
bị chấm.

Đại lượng quyết định là thông tin PHÍA MỜI THẦU và thường ĐÃ được step search tra về nằm trong
`thong_tin_bo_sung` của một nội dung anh em cùng tiêu chí (hoặc trong bảng neo). Nên quyết được
ngay ở decompose, một lần cho cả gói, thay vì lặp lại ở mỗi nhà thầu lúc chấm.

NGUYÊN TẮC AN TOÀN: bước này chỉ được phép BỎ BỚT việc khi chắc chắn. Mọi đường mơ hồ — không tìm
thấy đại lượng, không parse được số, các nguồn mâu thuẫn — đều trả `ket_luan=''` và để nội dung
được chấm BÌNH THƯỜNG. Không đụng `can_review` (cờ đó có thể khiến bước chấm short-circuit thành
"cần làm rõ" khi thong_tin_bo_sung rỗng, tức biến một nội dung chấm được thành không chấm nữa).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from experiment.decompose.schema import (
    KET_LUAN_AP_DUNG, KET_LUAN_CHUA_QUYET, KET_LUAN_KHONG_AP_DUNG,
)

# Bội số tiếng Việt đứng SAU con số ("50 triệu đồng").
_BOI_SO: list[tuple[str, int]] = [
    ("nghin ty", 10**12), ("nghin ti", 10**12),
    ("ty", 10**9), ("ti", 10**9),
    ("trieu", 10**6),
    ("nghin", 10**3), ("ngan", 10**3),
]

_PHEP = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "≤": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "≥": lambda a, b: a >= b,
    "=": lambda a, b: a == b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "≠": lambda a, b: a != b,
}

_RE_SO = re.compile(r"\d[\d.,]*")
_CUA_SO = 120   # số ký tự sau tên đại lượng còn được coi là "giá trị của nó"


def _norm_map(s: str) -> tuple[str, list[int]]:
    """Chuẩn hoá (thường, bỏ dấu, đ->d) KÈM bản đồ chỉ số về chuỗi gốc.

    Cần bản đồ vì tìm kiếm chạy trên bản bỏ dấu (chống lệch dấu/OCR) nhưng bằng chứng trả về phải
    là NGUYÊN VĂN có dấu để chuyên gia đọc được.
    """
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(s or ""):
        low = ch.lower().replace("đ", "d")
        for c in unicodedata.normalize("NFD", low):
            if unicodedata.category(c) != "Mn":
                out.append(c)
                idx.append(i)
    return "".join(out), idx


def _so_tu_chuoi(raw: str) -> float | None:
    """'939.000.000' -> 939000000.0 ; '1,5' -> 1.5 ; '50' -> 50.0. Không rõ -> None.

    Quy ước Việt: '.' là phân cách NGHÌN, ',' là thập phân. Nhưng '1.5' cũng hay gặp, nên chỉ coi
    '.' là phân cách nghìn khi MỌI nhóm sau dấu đầu tiên có đúng 3 chữ số.
    """
    raw = (raw or "").strip().rstrip(".,")
    if not raw:
        return None
    if "," in raw and "." in raw:                      # 1.234.567,89
        raw = raw.replace(".", "").replace(",", ".")
    elif "." in raw:
        nhom = raw.split(".")
        raw = "".join(nhom) if all(len(g) == 3 for g in nhom[1:]) else raw
    elif "," in raw:
        nhom = raw.split(",")
        raw = "".join(nhom) if all(len(g) == 3 for g in nhom[1:]) else raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_so(text: str) -> float | None:
    """Số ĐẦU TIÊN trong text, đã nhân bội số tiếng Việt đứng ngay sau. Không có -> None."""
    norm, _ = _norm_map(text)
    m = _RE_SO.search(norm)
    if not m:
        return None
    gia_tri = _so_tu_chuoi(m.group())
    if gia_tri is None:
        return None
    duoi = norm[m.end():m.end() + 24]
    for tu, nhan in _BOI_SO:
        if re.match(rf"\s*{tu}\b", duoi):
            return gia_tri * nhan
    return gia_tri


def tim_gia_tri(dai_luong: str, nguon_text: list[tuple[str, str]]) -> list[tuple[float, str]]:
    """Tìm giá trị của `dai_luong` trong các đoạn text đã resolve.

    nguon_text: [(nhãn nguồn, nội dung)]. Trả [(giá trị, bằng chứng nguyên văn)] — MỌI nơi tìm
    thấy, để bên gọi tự quyết khi các nguồn mâu thuẫn.
    """
    khoa, _ = _norm_map(dai_luong)
    khoa = " ".join(khoa.split())
    if not khoa:
        return []
    ket_qua: list[tuple[float, str]] = []
    for nhan, text in nguon_text:
        norm, idx = _norm_map(text)
        tu = 0
        while (vi := norm.find(khoa, tu)) != -1:
            tu = vi + len(khoa)
            duoi = norm[tu:tu + _CUA_SO].split("\n")[0]   # giá trị phải cùng dòng với tên
            m = _RE_SO.search(duoi)
            if not m:
                continue
            gia_tri = parse_so(duoi[m.start():])
            if gia_tri is None:
                continue
            dau, cuoi = idx[vi], idx[min(tu + m.end(), len(idx) - 1)]
            ket_qua.append((gia_tri, f"{nhan}: {text[dau:cuoi + 1].strip()}"))
    return ket_qua


def _nguon_text(crit: dict[str, Any], nd_bo_qua: dict[str, Any],
                anchors: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Nơi có thể chứa giá trị đại lượng: thong_tin_bo_sung của nội dung ANH EM + bảng neo.

    CHỈ lấy `thong_tin_bo_sung` (giá trị HSMT đã tra được), KHÔNG lấy `yeu_cau` — `yeu_cau` chứa
    chính mệnh đề điều kiện ("nhỏ hơn 50 triệu đồng") nên sẽ tự khớp với ngưỡng của chính nó.
    Bỏ qua chính nội dung đang xét vì lý do tương tự.
    """
    out: list[tuple[str, str]] = []
    for nd in crit.get("noi_dung_can_kiem_tra") or []:
        if nd is nd_bo_qua:
            continue
        tt = (nd.get("thong_tin_bo_sung") or "").strip()
        if tt:
            out.append((nd.get("noi_dung_kiem_tra") or "nội dung khác", tt))
    for ten, v in (anchors or {}).items():
        gia_tri = ((v or {}).get("gia_tri") or "").strip()
        if gia_tri:
            out.append(("bảng neo", f"{ten}: {gia_tri}"))
    return out


def doi_chieu_tieu_chi(crit: dict[str, Any], anchors: dict[str, Any] | None = None) -> int:
    """Đối chiếu điều kiện áp dụng cho MỌI nội dung của 1 tiêu chí — sửa TẠI CHỖ.

    Trả số nội dung bị kết luận KHÔNG áp dụng. Chạy sau step search (cần thong_tin_bo_sung đã có).
    """
    n_bo = 0
    for nd in crit.get("noi_dung_can_kiem_tra") or []:
        dk = nd.get("dieu_kien_ap_dung") or {}
        dai_luong = (dk.get("dai_luong") or "").strip()
        phep = (dk.get("phep_so_sanh") or "").strip()
        nguong_raw = (dk.get("nguong") or "").strip()
        if not (dai_luong and phep and nguong_raw):
            continue                                  # không có điều kiện -> không đụng tới

        # Mọi đường "chưa quyết được" phải ghi ket_luan TƯỜNG MINH: dict có thể tới từ JSON của LLM
        # hoặc từ DB nơi khoá này vắng mặt, mà bước chấm đọc dk.get('ket_luan') — để thiếu khoá thì
        # hợp đồng giữa hai bước phụ thuộc vào việc ai đã đi qua đây, rất dễ gãy ngầm.
        dk["ket_luan"] = KET_LUAN_CHUA_QUYET

        nguong = parse_so(nguong_raw)
        so_sanh = _PHEP.get(phep)
        if nguong is None or so_sanh is None:
            dk["can_cu"] = f"không đọc được điều kiện '{dai_luong} {phep} {nguong_raw}' — vẫn chấm"
            continue

        thay = tim_gia_tri(dai_luong, _nguon_text(crit, nd, anchors))
        if not thay:
            dk["can_cu"] = f"không tra được '{dai_luong}' trong HSMT đã bóc — vẫn chấm"
            continue
        gia_tris = {v for v, _ in thay}
        if len(gia_tris) > 1:                         # nguồn mâu thuẫn -> KHÔNG đoán
            dk["can_cu"] = (f"'{dai_luong}' ra nhiều giá trị khác nhau "
                            f"({', '.join(f'{v:,.0f}' for v in sorted(gia_tris))}) — vẫn chấm")
            continue

        gia_tri, bang_chung = thay[0]
        thoa = so_sanh(gia_tri, nguong)
        dk["ket_luan"] = KET_LUAN_AP_DUNG if thoa else KET_LUAN_KHONG_AP_DUNG
        dk["can_cu"] = (f"{dai_luong} = {gia_tri:,.0f} — điều kiện áp dụng là "
                        f"{phep} {nguong_raw} nên {'THOẢ' if thoa else 'KHÔNG THOẢ'} "
                        f"[căn cứ: {bang_chung}]")
        if not thoa:
            n_bo += 1
    return n_bo
