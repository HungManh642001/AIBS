# backend/experiment/chunking/tree.py
"""Dựng cây outline + duyệt block kèm ngữ cảnh section (stack heading đang mở)."""
from __future__ import annotations

from typing import Iterator

from .schema import Heading, Line, TableRegion, OutlineNode


def _pos(obj) -> tuple[int, float]:
    return (obj.page, obj.y0)


def build_outline(headings: list[Heading]) -> list[OutlineNode]:
    """Stack-based: heading có level nhỏ hơn là cha. page_end suy từ heading kế cùng/cao cấp."""
    roots: list[OutlineNode] = []
    stack: list[OutlineNode] = []
    for h in sorted(headings, key=_pos):
        node = OutlineNode(level=h.level, kind=h.kind, number=h.number, title=h.title,
                           page_start=h.page, page_end=h.page, section_path=[], children=[])
        while stack and stack[-1].level >= h.level:
            stack.pop()
        if stack:
            node.section_path = stack[-1].section_path + [h.title]
            stack[-1].children.append(node)
        else:
            node.section_path = [h.title]
            roots.append(node)
        stack.append(node)

    # page_end: tới ngay trước heading kế tiếp có level <= của nó (theo thứ tự phẳng).
    flat = sorted(headings, key=_pos)
    for i, h in enumerate(flat):
        end = None
        for nxt in flat[i + 1:]:
            if nxt.level <= h.level:
                end = nxt.page - 1 if nxt.page > h.page else h.page
                break
        _set_page_end(roots, h, end)
    return roots


def _set_page_end(nodes: list[OutlineNode], h: Heading, end: int | None) -> None:
    for n in nodes:
        if n.page_start == h.page and n.title == h.title and n.kind == h.kind:
            if end is not None:
                n.page_end = end
            return
        _set_page_end(n.children, h, end)


def iter_blocks_with_context(
    headings: list[Heading], blocks: list[Line | TableRegion]
) -> Iterator[tuple[Line | TableRegion, list[Heading]]]:
    """Trộn heading + block theo (page, y0); với mỗi block, trả stack heading đang mở."""
    events: list[tuple[tuple[int, float], int, object]] = []
    for h in headings:
        events.append((_pos(h), 0, h))       # heading ưu tiên trước block cùng vị trí
    for b in blocks:
        events.append((_pos(b), 1, b))
    events.sort(key=lambda e: (e[0], e[1]))

    stack: list[Heading] = []
    for _, kind, obj in events:
        if kind == 0:
            while stack and stack[-1].level >= obj.level:
                stack.pop()
            stack.append(obj)
        else:
            yield obj, list(stack)
