import pytest
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
