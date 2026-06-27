# backend/experiment/chunking/tests/test_end_to_end.py
import json
from pathlib import Path

from experiment.chunking.cli_chunk import run


def test_end_to_end_on_real_hsmt(sample_pdf, tmp_path):
    metrics = run(sample_pdf, str(tmp_path))

    outline = json.loads((tmp_path / "outline.json").read_text(encoding="utf-8"))
    chunks = [json.loads(l) for l in (tmp_path / "chunks.jsonl").read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert (tmp_path / "report.md").exists()

    # 1) Chuỗi Chương I..V dựng đúng (đơn điệu, không dính mục lục)
    chapters = [n["number"] for n in outline if n["kind"] == "chuong"]
    assert chapters[:5] == ["I", "II", "III", "IV", "V"]

    # 2) Chương III có đủ 4 nhóm tiêu chí
    assert {"hop_le", "nang_luc", "ky_thuat", "tai_chinh"} <= set(metrics["groups_found"])

    # 3) Có chunk bảng BDS quanh trang 23-26
    assert any(c["node_type"].startswith("table") and 23 <= c["page_start"] <= 26
               for c in chunks)

    # 4) Không chunk text nào vượt ngân sách
    assert metrics["over_budget"] == 0

    # 5) Chunk có truy vết section
    assert all(c["section_path"] for c in chunks if c["node_type"] == "text")
