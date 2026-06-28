from experiment.chunking.schema import Line
from experiment.chunking.headings import classify_heading, _norm


def _line(text, bold=True):
    return Line(page=27, text=text, bold=bold, size=11.0, y0=100.0, x0=70.0)


def test_norm_handles_d_stroke_before_nfd():
    assert _norm("Đánh giá tính hợp lệ") == "danh gia tinh hop le"


def test_real_headings_classified():
    cases = {
        "Phần 1. THỦ TỤC ĐẤU THẦU": ("phan", 0, "1"),
        "Chương III. TIÊU CHUẨN ĐÁNH GIÁ E-HSDT": ("chuong", 1, "III"),
        "Mục 2. Tiêu chuẩn đánh giá về năng lực": ("muc", 2, "2"),
        "Chương II. BẢNG DỮ LIỆU ĐẤU THẦU": ("chuong", 1, "II"),
    }
    for text, (kind, level, num) in cases.items():
        h = classify_heading(_line(text))
        assert h is not None and (h.kind, h.level, h.number) == (kind, level, num)


def test_inline_references_not_headings():
    # 'Phần việc' (v là chữ La Mã), 'Chương V chỉ nhằm...' phải bị regex loại
    for text in ["Phần việc", "Chương V chỉ nhằm mục đích mô tả", "Chương III;"]:
        assert classify_heading(_line(text)) is None


def test_non_bold_cross_reference_not_heading():
    # 'Mục 18.5 E-CDNT' khớp regex nhưng KHÔNG bold -> loại nhờ cờ bold
    assert classify_heading(_line("Mục 18.5 E-CDNT thì", bold=False)) is None
