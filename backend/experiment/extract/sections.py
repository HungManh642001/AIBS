# backend/experiment/extract/sections.py
"""Định vị Chương III và gom NỘI DUNG 4 nhóm (Mục 1–4). Tái dùng thư viện chunking."""
from __future__ import annotations

from experiment.chunking.layout import extract_lines, extract_tables
from experiment.chunking.headings import classify_heading, _norm
from experiment.chunking.structure import drop_toc_clusters, keep_monotonic_chapters
from experiment.chunking.tree import build_outline, iter_blocks_with_context
from experiment.chunking.schema import Line, TableRegion, OutlineNode

from .schema import Block, GroupContent
from .refs import detect_reference

# Map số Mục -> nhóm (thứ tự chuẩn theo Thông tư). Dùng làm fallback nếu từ khóa không khớp.
_DEFAULT_BY_NUM = {1: "hop_le", 2: "nang_luc", 3: "ky_thuat", 4: "tai_chinh"}
_KEYWORD_RULES = [
    ("hop le", "hop_le"), ("nang luc", "nang_luc"), ("kinh nghiem", "nang_luc"),
    ("ky thuat", "ky_thuat"), ("tai chinh", "tai_chinh"),
]
_ORDER = ["hop_le", "nang_luc", "ky_thuat", "tai_chinh"]


def _muc_group(title: str, num: int) -> str:
    norm = _norm(title)
    for needle, label in _KEYWORD_RULES:
        if needle in norm:
            return label
    return _DEFAULT_BY_NUM[num]


def _find_chuong(nodes: list[OutlineNode], number: str) -> OutlineNode | None:
    for n in nodes:
        if n.kind == "chuong" and n.number == number:
            return n
        found = _find_chuong(n.children, number)
        if found is not None:
            return found
    return None


def _consolidate(items: list) -> list[Block]:
    """Gộp các dòng text liên tiếp thành 1 Block text; mỗi bảng thành 1 Block table (rows verbatim)."""
    out: list[Block] = []
    buf: list[str] = []
    buf_pages: list[int] = []

    def flush() -> None:
        if buf:
            out.append(Block(type="text", page=[min(buf_pages), max(buf_pages)],
                             text="\n".join(buf)))
            buf.clear()
            buf_pages.clear()

    for b in items:
        if isinstance(b, TableRegion):
            flush()
            out.append(Block(type="table", page=[b.page, b.page], rows=b.rows))
        elif isinstance(b, Line):
            buf.append(b.text)
            buf_pages.append(b.page)
    flush()
    return out


def build_chuong3_groups(pdf_path: str) -> tuple[list[int], list[GroupContent]]:
    lines = extract_lines(pdf_path)
    tables, body_lines = extract_tables(pdf_path, lines)

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
    ch3 = _find_chuong(outline, "III")
    if ch3 is None:
        return [0, 0], []
    chuong3_page = [ch3.page_start, ch3.page_end]

    # Gom block theo Mục, chỉ trong Chương III.
    blocks: list = [*non_heading, *tables]
    per_muc: dict[str, dict] = {}
    for block, stack in iter_blocks_with_context(headings, blocks):
        chuong = next((h for h in stack if h.kind == "chuong"), None)
        if chuong is None or chuong.number != "III":
            continue
        muc = next((h for h in reversed(stack) if h.kind == "muc"), None)
        if muc is None:
            continue
        per_muc.setdefault(muc.title, {"muc": muc, "items": []})["items"].append(block)

    groups: list[GroupContent] = []
    for title, info in per_muc.items():
        muc = info["muc"]
        try:
            num = int(muc.number)
        except ValueError:
            continue
        if num not in _DEFAULT_BY_NUM:   # bỏ Mục 5/6/7
            continue
        out_blocks = _consolidate(info["items"])
        full_text = " ".join(b.text for b in out_blocks if b.type == "text")
        is_ref, target = detect_reference(full_text)
        p1 = max([muc.page] + [b.page[1] for b in out_blocks]) if out_blocks else muc.page
        groups.append(GroupContent(
            group=_muc_group(title, num), muc=title, muc_page=[muc.page, p1],
            is_reference=is_ref, ref_target=target, blocks=out_blocks,
        ))

    groups.sort(key=lambda g: _ORDER.index(g.group) if g.group in _ORDER else 99)
    return chuong3_page, groups
