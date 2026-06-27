from experiment.extract.refs import detect_reference


def test_detects_phan_reference():
    is_ref, target = detect_reference("Theo tài liệu đính kèm tại Phần 4. CÁC PHỤ LỤC")
    assert is_ref is True
    assert target == {"kind": "phan", "number": "4"}


def test_detects_chuong_reference_roman():
    is_ref, target = detect_reference("Đánh giá theo quy định tại Chương V của E-HSMT")
    assert is_ref is True
    assert target == {"kind": "chuong", "number": "V"}


def test_long_inline_content_is_not_reference():
    text = ("Nhà thầu phải đáp ứng đầy đủ các yêu cầu kỹ thuật sau đây. " * 12)
    is_ref, target = detect_reference(text)
    assert is_ref is False
    assert target is None


def test_empty_is_not_reference():
    assert detect_reference("") == (False, None)
