"""Render nội dung 4 nhóm ra Markdown cho người đọc/đối chiếu."""
from __future__ import annotations

from .schema import Block, GroupContent


def _cell(s: str | None) -> str:
    return (s or "").replace("\n", " ").replace("|", "\\|").strip()


def _table_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    out = []
    header = rows[0] + [""] * (width - len(rows[0]))
    out.append("| " + " | ".join(_cell(c) for c in header) + " |")
    out.append("| " + " | ".join(["---"] * width) + " |")
    for r in rows[1:]:
        r = r + [""] * (width - len(r))
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out)


def groups_to_markdown(doc: str, chuong3_page: list[int], groups: list[GroupContent]) -> str:
    lines = [f"# Nội dung tiêu chuẩn Chương III — {doc}",
             f"_Chương III: trang {chuong3_page[0]}–{chuong3_page[1]}_", ""]
    for g in groups:
        lines.append(f"## [{g.group}] {g.muc}  (tr {g.muc_page[0]}–{g.muc_page[1]})")
        if g.is_reference and g.ref_target:
            lines.append(f"> ⚠️ Tham chiếu sang **{g.ref_target['kind']} "
                         f"{g.ref_target['number']}** — chưa lần theo ở bước này.")
        lines.append("")
        for b in g.blocks:
            if b.type == "table":
                lines.append(_table_md(b.rows or []))
            else:
                lines.append(b.text or "")
            lines.append("")
    return "\n".join(lines)
