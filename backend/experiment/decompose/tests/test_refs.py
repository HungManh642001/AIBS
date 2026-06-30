from experiment.decompose.refs import extract_clause_refs


def test_extract_clause_refs_variants():
    # "Mục N.M E-CDNT" / "E-CDNT N.M" -> lấy cả mã đầy đủ lẫn mã lớn.
    assert extract_clause_refs("không vi phạm tại Mục 18.3 E-CDNT") == ["18.3", "18"]
    assert extract_clause_refs("hiệu lực theo E-CDNT 17.1") == ["17.1", "17"]
    assert extract_clause_refs("E-BDL 5 và Mục 5.1") == ["5", "5.1"]
    assert extract_clause_refs("không có mã nào") == []
    assert extract_clause_refs("") == []
