import json

from experiment.decompose.run_decompose import _load_bdl_rows, _load_scan_texts, _load_summaries


def test_load_bdl_rows_filters_clause_doc(tmp_path):
    p = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "a", "text": "E-CDNT 18.2 | 6.100.000", "clause_doc": "bdl"},
        {"chunk_id": "b", "text": "quy tắc", "clause_doc": "cdnt"},
        {"chunk_id": "c", "text": "text thường"},
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    got = _load_bdl_rows(str(p))
    assert [r["chunk_id"] for r in got] == ["a"]
    assert _load_bdl_rows(str(tmp_path / "missing.jsonl")) == []
    assert _load_bdl_rows(None) == []


def test_load_scan_texts_groups_by_source(tmp_path):
    p = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "a", "text": "E-CDNT 18.2 | 6.100.000", "clause_doc": "bdl", "source_doc": "hsmt"},
        {"chunk_id": "t1", "text": "Đóng thầu 09h00", "source_doc": "tbmt"},
        {"chunk_id": "t2", "text": "ngày 20/6/2025", "source_doc": "tbmt"},
        {"chunk_id": "h1", "text": "chỉ dẫn nhà thầu"},  # thiếu source_doc = hsmt
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    got = _load_scan_texts(str(p))
    assert got == {"tbmt": "Đóng thầu 09h00\nngày 20/6/2025"}   # chỉ nguồn scan, giữ thứ tự
    assert _load_scan_texts(None) == {}
    assert _load_scan_texts(str(tmp_path / "missing.jsonl")) == {}


def test_load_summaries(tmp_path):
    f = tmp_path / "source_summaries.json"
    f.write_text(json.dumps({"tbmt": "Thông báo mời thầu: thời gian", "x": ""}, ensure_ascii=False),
                 encoding="utf-8")
    got = _load_summaries(str(f))
    assert got == {"tbmt": "Thông báo mời thầu: thời gian"}     # entry rỗng bị loại
    assert _load_summaries(None) == {}
    assert _load_summaries(str(tmp_path / "missing.json")) == {}


def test_load_summaries_accepts_card(tmp_path):
    """Thẻ nguồn {tom_tat, cac_truong} -> phẳng hoá thành chuỗi hiển thị cho danh mục route."""
    f = tmp_path / "source_summaries.json"
    f.write_text(json.dumps({
        "tbmt": {"tom_tat": "Thông báo mời thầu", "cac_truong": ["thời điểm đóng/mở thầu", "địa điểm"]},
        "phu_luc": {"tom_tat": "Phụ lục kỹ thuật", "cac_truong": []},
        "rong": {"tom_tat": "", "cac_truong": []},
    }, ensure_ascii=False), encoding="utf-8")
    got = _load_summaries(str(f))
    assert got["tbmt"] == "Thông báo mời thầu (chứa: thời điểm đóng/mở thầu, địa điểm)"
    assert got["phu_luc"] == "Phụ lục kỹ thuật"
    assert "rong" not in got                                     # thẻ rỗng bị loại
