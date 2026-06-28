# backend/experiment/extract/cli_extract.py
"""CLI: HSMT PDF-text -> chuong3_groups.json + .md + report.md (nội dung 4 nhóm Chương III)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sections import build_chuong3_groups
from .schema import groups_to_json
from .render import groups_to_markdown


def run(pdf_path: str, out_dir: str) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = Path(pdf_path).stem

    chuong3_page, groups = build_chuong3_groups(pdf_path)

    (out / "chuong3_groups.json").write_text(
        groups_to_json(doc, chuong3_page, groups), encoding="utf-8")
    (out / "chuong3_groups.md").write_text(
        groups_to_markdown(doc, chuong3_page, groups), encoding="utf-8")

    by_group = {g.group: g for g in groups}
    metrics = {
        "doc": doc,
        "chuong3_page": chuong3_page,
        "n_groups": len(groups),
        "groups": [g.group for g in groups],
        "nang_luc_has_table": any(
            b.type == "table" for b in by_group.get("nang_luc").blocks
        ) if "nang_luc" in by_group else False,
        "ky_thuat_is_reference": by_group["ky_thuat"].is_reference if "ky_thuat" in by_group else False,
    }

    report = [f"# Báo cáo trích nội dung Chương III — {doc}", "",
              f"- Chương III: trang {chuong3_page[0]}–{chuong3_page[1]}",
              f"- Số nhóm trích được: **{len(groups)}** ({', '.join(metrics['groups'])})", ""]
    for g in groups:
        n_text = sum(1 for b in g.blocks if b.type == "text")
        n_tab = sum(1 for b in g.blocks if b.type == "table")
        ref = f"  ⚠️ tham chiếu {g.ref_target}" if g.is_reference else ""
        report.append(f"- **{g.group}** — {g.muc} (tr {g.muc_page[0]}–{g.muc_page[1]}): "
                      f"{n_text} block text, {n_tab} block bảng{ref}")
    (out / "report.md").write_text("\n".join(report), encoding="utf-8")
    return metrics


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Trích nội dung 4 nhóm tiêu chuẩn Chương III")
    ap.add_argument("--pdf", required=True, help="đường dẫn HSMT PDF-text")
    ap.add_argument("--out", default="experiment/out", help="thư mục artefact")
    args = ap.parse_args(argv)
    metrics = run(args.pdf, args.out)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
