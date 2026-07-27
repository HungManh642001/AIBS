"""Trích text TẤT ĐỊNH từ PDF có sẵn text nhúng — đường thay thế vision cho trang không phải scan.

VÌ SAO: vision đọc bảng không ổn định — cùng một trang, hai lần chạy có thể ra khác nhau (thiếu
dòng, gộp ô, đổi cách biểu diễn). Với trang PDF đã có text nhúng thì mọi ký tự đã nằm sẵn trong
file: đọc thẳng cho kết quả chính xác 100%, tái lập tuyệt đối và không tốn call nào.

KHI NÀO KHÔNG dùng đường này (trả None -> để vision đọc ảnh):
- trang gần như không có text nhúng: đó là bản scan, chỉ vision đọc được;
- trang CÓ ẢNH NHÚNG: ảnh có thể là chữ ký/con dấu, mà cờ `co_chu_ky`/`co_dau` chỉ vision mới ghi
  được. Đo trên hồ sơ thật: trang bảng giá luôn 0 ảnh, trang có chữ ký luôn >= 1 ảnh — nên ngưỡng
  "0 ảnh" tách được đúng hai nhóm mà không đánh mất tín hiệu thị giác nào.
"""
from __future__ import annotations

import fitz

NGUONG_TEXT = 200      # dưới ngưỡng này coi như trang scan (chỉ còn số trang, watermark...)
_O = " | "             # phân tách ô trong một hàng bảng


def _bang_thanh_text(bang: object) -> str:
    """Bảng -> mỗi HÀNG một dòng, ô cách nhau ' | ', GIỮ ô trống để không lệch cột."""
    dong: list[str] = []
    for hang in bang.extract():                     # type: ignore[attr-defined]
        o = [(str(c) if c is not None else "").replace("\n", " ").strip() for c in hang]
        if any(o):
            dong.append(_O.join(o))
    return "\n".join(dong)


def trich_trang_tat_dinh(page: fitz.Page) -> str | None:
    """Text của trang, hoặc None nếu trang phải đi đường vision (xem docstring module)."""
    text = page.get_text() or ""
    if len(text.strip()) < NGUONG_TEXT or page.get_images():
        return None

    bangs = page.find_tables().tables
    if not bangs:
        return text

    # Chữ NGOÀI bảng (tiêu đề, ghi chú) vẫn phải giữ — lọc theo bbox của bảng.
    phan: list[str] = []
    ngoai = _text_ngoai_bang(page, bangs)
    if ngoai:
        phan.append(ngoai)
    phan.extend(_bang_thanh_text(b) for b in bangs)
    return "\n".join(p for p in phan if p.strip())


def _text_ngoai_bang(page: fitz.Page, bangs: list) -> str:
    """Chữ nằm ngoài mọi bbox bảng — tiêu đề/ghi chú không được rơi mất."""
    hop = [fitz.Rect(b.bbox) for b in bangs]
    giu: list[str] = []
    for khoi in page.get_text("blocks"):
        x0, y0, x1, y1, noi_dung = khoi[0], khoi[1], khoi[2], khoi[3], khoi[4]
        r = fitz.Rect(x0, y0, x1, y1)
        if any(r.intersects(h) for h in hop):
            continue
        if noi_dung.strip():
            giu.append(noi_dung.strip())
    return "\n".join(giu)
