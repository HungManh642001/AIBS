import json

from experiment.decompose.run_decompose import (
    _load_bdl_rows,
    _load_form_texts,
    _load_scan_texts,
    _load_summaries,
)


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


def test_load_form_texts_inherits_open_form(tmp_path):
    """Mẫu tách nhiều chunk: chunk bảng phía sau KHÔNG có từ khóa mẫu -> kế thừa mẫu đang mở;
    marker mẫu mới cắt kế thừa; chunk ngoài chương Biểu mẫu reset."""
    p = tmp_path / "chunks.jsonl"
    bm = ["Chương IV. BIỂU MẪU MỜI THẦU VÀ DỰ THẦU"]
    rows = [
        {"chunk_id": "c0", "text": "E-CDNT 18.2 | quy tắc", "section_path": ["Chương I. CHỈ DẪN NHÀ THẦU"]},
        {"chunk_id": "f1", "text": "Mẫu số 05C.1. BẢNG CHÀO GIÁ\nKính gửi...", "section_path": bm},
        {"chunk_id": "f2", "text": "STT | Hạng mục | Đơn giá | Thành tiền", "section_path": bm},
        {"chunk_id": "f3", "text": "1 | Máy chủ | ... | ...", "section_path": bm},
        {"chunk_id": "f4", "text": "Mẫu số 06. BẢO LÃNH DỰ THẦU", "section_path": bm},
        {"chunk_id": "c9", "text": "Yêu cầu kỹ thuật phần 4", "section_path": ["Yêu cầu kỹ thuật"]},
    ]
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    got = _load_form_texts(str(p))

    # 3 chunk của mẫu 05C.1 gộp trọn (kể cả 2 chunk bảng không từ khóa)
    assert "BẢNG CHÀO GIÁ" in got["05c.1"] and "Đơn giá" in got["05c.1"] and "Máy chủ" in got["05c.1"]
    assert "BẢO LÃNH" not in got["05c.1"]        # marker 'Mẫu số 06' cắt kế thừa
    assert "06" in got
    assert "Yêu cầu kỹ thuật" not in "".join(got.values())  # ngoài Biểu mẫu không dính
    assert _load_form_texts(None) == {}


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
