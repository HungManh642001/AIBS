"""Trích tất định từ PDF có text nhúng — thay vision cho trang bảng (chính xác + tái lập 100%).

Vision đọc bảng không ổn định: cùng trang, hai lần chạy ra khác nhau (thiếu dòng/sai cấu trúc).
Trang nào có text nhúng và KHÔNG có ảnh nhúng thì đọc thẳng, khỏi qua LLM.
"""
import fitz

from experiment.evaluate.pdf_text import NGUONG_TEXT, trich_trang_tat_dinh


def _trang_bang(n_hang: int = 2, chu_ngoai_bang: str = "") -> fitz.Page:
    """PDF 1 trang có bảng vẽ đường kẻ (find_tables nhận diện được)."""
    d = fitz.open()
    pg = d.new_page()
    if chu_ngoai_bang:
        pg.insert_text((50, 40), chu_ngoai_bang)
    xs = [50, 200, 350]
    ys = [60 + 30 * i for i in range(n_hang + 1)]
    for x in xs:
        pg.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]))
    for y in ys:
        pg.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y))
    # fontsize nhỏ để chuỗi dài nằm gọn trong ô (tràn ô thì PDF không lưu chữ -> hụt ngưỡng text)
    pg.insert_text((55, ys[0] + 20), "STT", fontsize=5)
    pg.insert_text((205, ys[0] + 20), "Ten hang " + "x" * 60, fontsize=5)
    for i in range(1, n_hang):
        pg.insert_text((55, ys[i] + 20), str(i), fontsize=5)
        pg.insert_text((205, ys[i] + 20), f"May chu {i} " + "y" * 60, fontsize=5)
    data = d.tobytes()
    d.close()
    return fitz.open(stream=data, filetype="pdf")[0]


def _trang_chu(text: str) -> fitz.Page:
    """Mỗi dòng <= 60 ký tự để không tràn khỏi khổ giấy (tràn thì PDF không lưu chữ đó)."""
    d = fitz.open()
    pg = d.new_page()
    dong = [text[i:i + 60] for i in range(0, len(text), 60)] if text else []
    for i, x in enumerate(dong):
        pg.insert_text((50, 60 + 15 * i), x)
    data = d.tobytes()
    d.close()
    return fitz.open(stream=data, filetype="pdf")[0]


def test_trang_bang_ra_dang_hang_cot_on_dinh():
    got = trich_trang_tat_dinh(_trang_bang(n_hang=3))
    assert got is not None
    dong = [d for d in got.splitlines() if "|" in d]
    assert len(dong) == 3                       # đúng số hàng, không gộp không bỏ
    assert dong[0].count("|") == 1              # 2 cột -> 1 dấu phân tách
    assert "STT" in dong[0] and "May chu 1" in dong[1]


def test_ket_qua_tai_lap_100_phan_tram():
    """Cùng trang, gọi 2 lần -> y hệt (thứ mà vision không bảo đảm được)."""
    assert trich_trang_tat_dinh(_trang_bang(3)) == trich_trang_tat_dinh(_trang_bang(3))


def test_giu_chu_nam_ngoai_bang():
    """Tiêu đề/ghi chú ngoài bảng không được rơi mất khi xuất bảng."""
    got = trich_trang_tat_dinh(_trang_bang(3, chu_ngoai_bang="BANG GIA DU THAU" + "y" * 200))
    assert got is not None and "BANG GIA DU THAU" in got


def test_trang_chu_thuong_lay_nguyen_text():
    got = trich_trang_tat_dinh(_trang_chu("DON DU THAU\n" + "Noi dung dong nay dai. " * 20))
    assert got is not None and "DON DU THAU" in got and "|" not in got


def test_trang_it_chu_tra_none_de_di_duong_vision():
    """Trang scan (không text nhúng) hoặc gần như trống -> phải để vision đọc ảnh."""
    assert trich_trang_tat_dinh(_trang_chu("")) is None
    assert trich_trang_tat_dinh(_trang_chu("vai chu")) is None
    assert NGUONG_TEXT > 0


def test_trang_co_anh_nhung_tra_none_de_giu_co_chu_ky():
    """Ảnh nhúng = có thể là chữ ký/con dấu -> KHÔNG đi tất định, nếu không mất tín hiệu thị giác.

    Số liệu hồ sơ thật: trang bảng giá luôn 0 ảnh; trang có chữ ký luôn >= 1 ảnh.
    """
    d = fitz.open()
    pg = d.new_page()
    pg.insert_text((50, 60), "DON DU THAU " * 30)
    px = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), 0)
    pg.insert_image(fitz.Rect(50, 200, 150, 250), pixmap=px)     # giả chữ ký/dấu
    data = d.tobytes()
    d.close()
    trang = fitz.open(stream=data, filetype="pdf")[0]
    assert trang.get_images()                                    # tiền đề của test
    assert trich_trang_tat_dinh(trang) is None
