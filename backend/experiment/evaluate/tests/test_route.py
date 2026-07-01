from experiment.evaluate.route import route_pages, pages_text, has_visual_check
from experiment.evaluate.schema import PageRecord


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def test_route_selects_matching_doc_type():
    pages = [_p(1, "don_du_thau", "đơn"), _p(2, "bao_dam_du_thau", "bảo lãnh 6tr"), _p(3, "khac", "x")]
    got = route_pages(pages, "bao_dam_du_thau")
    assert [p.trang for p in got] == [2]
    assert route_pages(pages, "khong_co") == []      # không loại nào khớp -> rỗng (thiếu hồ sơ)


def test_pages_text_joins_with_page_markers():
    txt = pages_text([_p(2, "bao_dam_du_thau", "bảo lãnh 6tr")])
    assert "[Trang 2]" in txt and "bảo lãnh 6tr" in txt


def test_has_visual_check():
    assert has_visual_check("chữ ký & đóng dấu") is True
    assert has_visual_check("con dấu") is True
    assert has_visual_check("đối chiếu") is False
