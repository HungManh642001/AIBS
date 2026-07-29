import pytest
from services import json_utils as ju
from services.json_utils import extract_json, clamp_page_refs


def test_extract_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_from_fence():
    raw = "Suy luận: ok\n```json\n{\"result\": \"PASS\"}\n```"
    assert extract_json(raw) == {"result": "PASS"}


def test_extract_ignores_prose_around_object():
    raw = 'Tôi kết luận như sau: {"x": [1, 2]} . Hết.'
    assert extract_json(raw) == {"x": [1, 2]}


def test_extract_strips_trailing_comma():
    assert extract_json('{"a": 1, "b": [2, 3,],}') == {"a": 1, "b": [2, 3]}


def test_extract_nested_braces():
    assert extract_json('{"a": {"b": 1}}') == {"a": {"b": 1}}


def test_extract_empty_raises():
    with pytest.raises(ValueError):
        extract_json("")


def test_extract_no_object_raises():
    with pytest.raises(ValueError):
        extract_json("không có json ở đây")


def test_clamp_filters_and_bounds():
    assert clamp_page_refs([1, 2, "x", 0, -3, True], max_page=3) == [1, 2]
    assert clamp_page_refs([1, 9], max_page=3) == [1]
    assert clamp_page_refs([1, 9], max_page=0) == [1, 9]   # 0 = không biết số trang -> chỉ lọc >=1
    assert clamp_page_refs(None, max_page=3) == []


# ---- vá escape hỏng (LLM nhả LaTeX / đường dẫn Windows vào giữa chuỗi) ----
def test_va_escape_cuu_duoc_latex_tu_log_that():
    """Ca THẬT từ server: model viết '$\\ge$' — '\\g' không phải escape JSON hợp lệ.

    Trước đây cả object bị vứt dù nội dung đọc được hoàn toàn.
    """
    raw = ('{"thong_tin_bo_sung": "Ngày ký thư bảo lãnh $\\ge$ 10:45, 24/03/2026.",'
           ' "nguon": "TBMT", "can_review": false}')
    d = ju.extract_json(raw)
    assert d["thong_tin_bo_sung"] == "Ngày ký thư bảo lãnh $\\ge$ 10:45, 24/03/2026."
    assert d["nguon"] == "TBMT" and d["can_review"] is False


def test_va_escape_duong_dan_windows():
    d = ju.extract_json(r'{"db": "C:\Users\abes\storage"}')
    assert d["db"] == r"C:\Users\abes\storage"


def test_va_escape_giu_nguyen_escape_hop_le():
    """Không được đụng \\n \\t \\" \\\\ — vá bừa sẽ biến xuống dòng thành chữ 'n'."""
    d = ju.extract_json(r'{"a": "dòng1\ndòng2", "b": "tab\there", "c": "nháy \" trong chuỗi", "d": "gạch \\ đơn"}')
    assert d["a"] == "dòng1\ndòng2"
    assert d["b"] == "tab\there"
    assert d["c"] == 'nháy " trong chuỗi'
    assert d["d"] == "gạch \\ đơn"


def test_va_escape_khong_nham_nhay_da_escape_la_dong_chuoi():
    r"""`\"` bên trong chuỗi KHÔNG được tính là dấu đóng chuỗi, kẻo `\ge` sau đó bị bỏ sót."""
    d = ju.extract_json(r'{"a": "ông \"A\" nói $\ge$ 5"}')
    assert d["a"] == r'ông "A" nói $\ge$ 5'


def test_va_escape_khong_dung_toi_dau_gach_ngoai_chuoi():
    assert ju.va_escape(r'{"a": 1}') == r'{"a": 1}'


def test_bao_dung_benh_khi_ngoac_can_bang():
    """Ngoặc cân bằng mà parse hỏng -> KHÔNG được báo 'không cân bằng ngoặc'.

    Thông báo sai bệnh từng làm mất thời gian truy nhầm hướng một lỗi escape.
    """
    with pytest.raises(ValueError) as e:
        ju.extract_json('{"a": "x" "b": 2}')       # thiếu dấu phẩy, ngoặc vẫn cân bằng
    assert "không cân bằng ngoặc" not in str(e.value)


def test_van_bao_khong_can_bang_khi_that_su_thieu_ngoac():
    with pytest.raises(ValueError) as e:
        ju.extract_json('không có json ở đây { "a"')
    assert "preview cuối" in str(e.value)
