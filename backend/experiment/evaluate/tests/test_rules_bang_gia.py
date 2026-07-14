"""B3 — luật bang_gia_khop_webform: bảng giá vendor ↔ dòng đúng nhà thầu trong webform chung."""
from experiment.evaluate.rules.bang_gia_khop_webform import find_vendor_pages
from experiment.evaluate.schema import PageRecord, VendorContext


def _p(trang, text, loai="webform"):
    return PageRecord(file="webform.pdf", trang=trang, loai_ho_so=loai, text=text)


_WEBFORM = [
    _p(1, "KẾT QUẢ MỞ THẦU\nSTT | Nhà thầu | Giá dự thầu"),
    _p(2, "1 | Công ty TNHH Xây dựng ABC | 1.200.000.000\n2 | Công ty CP DEF | 1.150.000.000"),
    _p(3, "3 | Liên danh GHI-JKL (MST 0312345678) | 1.100.000.000"),
]


def test_find_vendor_pages_by_name_normalized():
    """Khớp tên bỏ dấu/hoa thường; chỉ trả trang chứa nhà thầu đang chấm."""
    ctx = VendorContext(ten="Công ty TNHH XÂY DỰNG abc")
    assert [p.trang for p in find_vendor_pages(_WEBFORM, ctx)] == [2]


def test_find_vendor_pages_by_mst_and_alias():
    assert [p.trang for p in find_vendor_pages(_WEBFORM, VendorContext(ten="Không khớp tên",
                                                                       ma_so_thue="0312345678"))] == [3]
    assert [p.trang for p in find_vendor_pages(_WEBFORM, VendorContext(ten="XYZ",
                                                                       aliases=["công ty cp def"]))] == [2]


def test_find_vendor_pages_no_match_empty():
    assert find_vendor_pages(_WEBFORM, VendorContext(ten="Công ty Ma", ma_so_thue="999")) == []
    assert find_vendor_pages([], VendorContext(ten="ABC")) == []
