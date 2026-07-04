from experiment.decompose.refs import extract_clause_refs, extract_form_refs


def test_extract_clause_refs_variants():
    # "Mục N.M E-CDNT" / "E-CDNT N.M" -> lấy cả mã đầy đủ lẫn mã lớn.
    assert extract_clause_refs("không vi phạm tại Mục 18.3 E-CDNT") == ["18.3", "18"]
    assert extract_clause_refs("hiệu lực theo E-CDNT 17.1") == ["17.1", "17"]
    assert extract_clause_refs("E-BDL 5 và Mục 5.1") == ["5", "5.1"]
    assert extract_clause_refs("không có mã nào") == []
    assert extract_clause_refs("") == []


def test_extract_form_refs():
    # 'Mẫu số 01' / 'mẫu 04A' -> mã mẫu thường hóa, để định tuyến need vào chunk Biểu mẫu.
    assert extract_form_refs("Đơn dự thầu phải đúng Mẫu số 01 Chương IV") == ["01"]
    assert extract_form_refs("theo mẫu 04A và Mẫu số 04B") == ["04a", "04b"]
    assert extract_form_refs("Giá trị bảo lãnh theo E-BDL 18.2") == []
    assert extract_form_refs("") == []
