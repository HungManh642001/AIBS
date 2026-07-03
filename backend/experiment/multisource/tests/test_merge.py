import json

from experiment.multisource.merge import merge_chunk_files


def test_merge_tags_source_and_appends(tmp_path):
    hsmt = tmp_path / "chunks.jsonl"
    hsmt.write_text(
        json.dumps({"chunk_id": "hsmt-1", "text": "E-CDNT ...", "section_path": ["Chỉ dẫn"]}) + "\n",
        encoding="utf-8")
    extra = [{"chunk_id": "tbmt-p1-0", "text": "đóng thầu 09h00", "section_path": ["Thông báo mời thầu"],
              "source_doc": "tbmt"}]
    out = tmp_path / "merged.jsonl"

    n = merge_chunk_files(str(hsmt), extra, str(out))

    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert n == 2 and len(lines) == 2
    by_id = {c["chunk_id"]: c for c in lines}
    assert by_id["hsmt-1"]["source_doc"] == "hsmt"      # gắn mặc định
    assert by_id["tbmt-p1-0"]["source_doc"] == "tbmt"   # giữ nguyên
