import json

from experiment.decompose.run_decompose import _load_bdl_rows


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
