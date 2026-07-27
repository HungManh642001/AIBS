from experiment.evaluate.route import inventory_pages, pages_by_type, pages_text, route_pages
from experiment.evaluate.schema import HoSoNhanDuoc, PageRecord


def _p(trang, loai, text, co_chu_ky=False, co_dau=False, file="f.pdf"):
    return PageRecord(file=file, trang=trang, loai_ho_so=loai, text=text,
                      co_chu_ky=co_chu_ky, co_dau=co_dau)


def test_inventory_pages_groups_files_and_counts():
    """Danh mục hồ sơ nhận được: loại chuẩn hoá -> file (khử trùng, giữ thứ tự) -> số trang."""
    inv = inventory_pages([_p(1, "Đơn_Dự_Thầu", "a", file="don.pdf"),
                           _p(2, "don_du_thau", "b", file="don.pdf"),
                           _p(1, "bang_gia", "c", file="bg.pdf")])
    assert inv == [HoSoNhanDuoc("don_du_thau", ["don.pdf"], 2),
                   HoSoNhanDuoc("bang_gia", ["bg.pdf"], 1)]
    assert inventory_pages([]) == []


def test_route_selects_matching_doc_type():
    pages = [_p(1, "don_du_thau", "đơn"), _p(2, "bao_dam_du_thau", "bảo lãnh 6tr"), _p(3, "khac", "x")]
    got = route_pages(pages, "bao_dam_du_thau")
    assert [p.trang for p in got] == [2]
    assert route_pages(pages, "khong_co") == []      # không loại nào khớp -> rỗng (thiếu hồ sơ)


def test_pages_by_type_groups_normalized_keys():
    """Nhóm trang theo loại hồ sơ chuẩn hoá (bỏ dấu/hoa thường), giữ thứ tự trang."""
    pages = [_p(1, "Đơn_Dự_Thầu", "đơn tr1"), _p(2, "bao_dam_du_thau", "bảo lãnh"),
             _p(3, "don_du_thau", "đơn tr3"), _p(4, "", "trống")]
    got = pages_by_type(pages)
    assert [p.trang for p in got["don_du_thau"]] == [1, 3]   # hoa/có dấu về cùng key
    assert [p.trang for p in got["bao_dam_du_thau"]] == [2]
    assert "" not in got                                      # loại rỗng bị bỏ
    assert pages_by_type([]) == {}


def test_pages_text_joins_with_page_markers():
    txt = pages_text([_p(2, "bao_dam_du_thau", "bảo lãnh 6tr")])
    assert "[Trang 2]" in txt and "bảo lãnh 6tr" in txt


def test_pages_text_surfaces_visual_flags():
    txt = pages_text([_p(1, "bao_dam_du_thau", "thư bảo lãnh", co_chu_ky=True, co_dau=True)])
    assert "có chữ ký" in txt and "có đóng dấu" in txt   # eval biết có chữ ký/dấu dù không đính ảnh


def test_pages_text_hien_canh_bao_boc_thieu():
    """Trang nghi bóc thiếu phải nói ra trong text — luật đọc thấy mới thận trọng được."""
    from experiment.evaluate.route import pages_text
    from experiment.evaluate.schema import PageRecord

    p = PageRecord(file="bg.pdf", trang=3, loai_ho_so="bang_gia", text="1 | May chu | 100",
                   canh_bao="số cột không đều: 2/5 hàng lệch")
    got = pages_text([p])
    assert "CẢNH BÁO" in got and "số cột không đều" in got
    assert "1 | May chu | 100" in got            # vẫn giữ nguyên nội dung đọc được
