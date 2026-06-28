# backend/experiment/chunking/cli_chunk.py
"""CLI: HSMT PDF-text -> outline.json + chunks.jsonl + report.md (artefact soi tay)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema import chunks_to_jsonl, outline_to_json
from .layout import extract_lines, extract_tables
from .headings import classify_heading
from .structure import drop_toc_clusters, keep_monotonic_chapters
from .tree import build_outline
from .chunker import make_chunks

_MAX_CHARS = 1800


def run(pdf_path: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = Path(pdf_path).stem

    lines = extract_lines(pdf_path)
    tables, body_lines = extract_tables(pdf_path, lines)

    # Tách heading khỏi dòng body để không nhân đôi text heading vào chunk.
    headings = []
    non_heading: list = []
    for l in body_lines:
        h = classify_heading(l)
        if h is not None:
            headings.append(h)
        else:
            non_heading.append(l)
    headings = keep_monotonic_chapters(drop_toc_clusters(headings))

    outline = build_outline(headings)
    chunks = make_chunks(headings, non_heading, tables, doc=doc, max_chars=_MAX_CHARS)

    (out / "outline.json").write_text(outline_to_json(outline), encoding="utf-8")
    (out / "chunks.jsonl").write_text(chunks_to_jsonl(chunks), encoding="utf-8")

    groups_found = sorted({c.group_hint for c in chunks if c.group_hint != "unknown"})
    over_budget = sum(1 for c in chunks if c.node_type == "text" and c.char_len > _MAX_CHARS)
    bds_pages = sorted({c.page_start for c in chunks
                        if c.node_type.startswith("table") and 23 <= c.page_start <= 26})
    metrics = {
        "n_chunks": len(chunks),
        "n_chapters": sum(1 for h in headings if h.kind == "chuong"),
        "groups_found": groups_found,
        "bds_table_pages": bds_pages,
        "over_budget": over_budget,
    }

    # Chuyển outline sang dict để dùng key-access trong report loop.
    outline_dicts = json.loads(outline_to_json(outline))
    report = [
        f"# Báo cáo chunking — {doc}",
        "",
        f"- Tổng chunk: **{metrics['n_chunks']}**",
        f"- Số Chương dựng được: **{metrics['n_chapters']}**",
        f"- Nhóm tiêu chí tìm thấy: **{', '.join(groups_found) or 'không'}**",
        f"- Trang bảng BDS (23-26): **{bds_pages or 'không'}**",
        f"- Chunk text vượt {_MAX_CHARS} ký tự: **{over_budget}**",
        "",
        "## Outline (Chương / Mục)",
    ]
    for n in outline_dicts:
        if n["kind"] in ("chuong", "phan"):
            report.append(f"- {n['title']}  (tr {n['page_start']}–{n['page_end']})")
            for c in n.get("children", []):
                report.append(f"    - {c['title']}  (tr {c['page_start']}–{c['page_end']})")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    return metrics


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Chunk HSMT PDF-text phân cấp")
    ap.add_argument("--pdf", default="experiment/samples/E-HSMT.pdf", help="đường dẫn HSMT PDF-text")
    ap.add_argument("--out", default="experiment/out", help="thư mục artefact")
    args = ap.parse_args(argv)
    metrics = run(args.pdf, args.out)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
