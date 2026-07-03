import json

import experiment.multisource.run_rubric as rr


async def test_run_multi_orchestration(tmp_path, monkeypatch):
    calls = []

    def fake_chunk(pdf, out):  # tạo chunks.jsonl HSMT giả
        p = f"{out}/chunks.jsonl"
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"chunk_id": "hsmt-1", "text": "E-CDNT", "section_path": ["Chỉ dẫn"]}) + "\n")
        calls.append("chunk"); return {"n_chunks": 1}

    def fake_extract(pdf, out):
        with open(f"{out}/chuong3_groups.json", "w", encoding="utf-8") as f:
            json.dump({"doc": "HSMT", "groups": []}, f)
        calls.append("extract"); return {}

    async def fake_ocr(pdf_path, source_doc, vision_fn=None, **kw):
        calls.append(f"ocr:{source_doc}")
        return [{"chunk_id": "tbmt-p1-0", "text": "đóng thầu 09h00", "section_path": ["Thông báo mời thầu"],
                 "source_doc": "tbmt"}]

    def fake_index(chunks_path, db_path, out_dir, **kw):
        n = sum(1 for _ in open(chunks_path, encoding="utf-8"))
        calls.append(f"index:{n}"); return {"n_points": n}

    async def fake_decompose(groups_path, db_path, out_dir, **kw):
        calls.append("decompose"); return {"n_criteria": 0}

    monkeypatch.setattr(rr, "chunk_run", fake_chunk)
    monkeypatch.setattr(rr, "extract_run", fake_extract)
    monkeypatch.setattr(rr, "ocr_scan_to_chunks", fake_ocr)
    monkeypatch.setattr(rr, "index_run", fake_index)
    monkeypatch.setattr(rr, "decompose_run", fake_decompose)

    hsmt = tmp_path / "hsmt.pdf"; hsmt.write_bytes(b"%PDF-1.4")
    tbmt = tmp_path / "tbmt.pdf"; tbmt.write_bytes(b"%PDF-1.4")

    metrics = await rr.run_multi(str(hsmt), [("tbmt", str(tbmt))], str(tmp_path / "out"))

    assert calls == ["chunk", "extract", "ocr:tbmt", "index:2", "decompose"]  # thứ tự + merge (2 chunk)
    assert metrics["n_criteria"] == 0
