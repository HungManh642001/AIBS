from experiment.evaluate.route import route_pages, pages_text
from experiment.evaluate.schema import PageRecord


def _p(trang, loai, text, co_chu_ky=False, co_dau=False):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text,
                      co_chu_ky=co_chu_ky, co_dau=co_dau)


def test_route_selects_matching_doc_type():
    pages = [_p(1, "don_du_thau", "đơn"), _p(2, "bao_dam_du_thau", "bảo lãnh 6tr"), _p(3, "khac", "x")]
    got = route_pages(pages, "bao_dam_du_thau")
    assert [p.trang for p in got] == [2]
    assert route_pages(pages, "khong_co") == []      # không loại nào khớp -> rỗng (thiếu hồ sơ)


def test_pages_text_joins_with_page_markers():
    txt = pages_text([_p(2, "bao_dam_du_thau", "bảo lãnh 6tr")])
    assert "[Trang 2]" in txt and "bảo lãnh 6tr" in txt


def test_pages_text_surfaces_visual_flags():
    txt = pages_text([_p(1, "bao_dam_du_thau", "thư bảo lãnh", co_chu_ky=True, co_dau=True)])
    assert "có chữ ký" in txt and "có đóng dấu" in txt   # eval biết có chữ ký/dấu dù không đính ảnh
