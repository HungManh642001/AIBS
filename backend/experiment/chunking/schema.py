"""Hợp đồng dữ liệu cho pipeline chunking phân cấp HSMT."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

LEVEL_PHAN = 0
LEVEL_CHUONG = 1
LEVEL_MUC = 2
LEVEL_DIEU = 3


@dataclass
class Line:
    """Một dòng văn bản đã gộp span, kèm tín hiệu layout."""
    page: int      # 1-based
    text: str
    bold: bool
    size: float
    y0: float      # toạ độ đỉnh dòng (để sắp xếp đọc + gán section)
    x0: float


@dataclass
class TableRegion:
    """Một bảng do find_tables() phát hiện, kèm bbox dọc để lọc dòng trùng."""
    page: int
    y0: float
    y1: float
    rows: list[list[str]]


@dataclass
class Heading:
    kind: str      # phan | chuong | muc | dieu
    level: int
    number: str    # đã chuẩn hoá hoa, ví dụ "III", "2"
    title: str
    page: int
    y0: float


@dataclass
class OutlineNode:
    level: int
    kind: str
    number: str
    title: str
    page_start: int
    page_end: int
    section_path: list[str]
    children: list["OutlineNode"] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    doc: str
    text: str
    section_path: list[str]
    chapter_no: str | None
    section_title: str | None   # tiêu đề Mục đang chứa block
    level: int
    heading_number: str | None
    page_start: int
    page_end: int
    node_type: str              # text | table | table_row_group
    group_hint: str             # hop_le | nang_luc | ky_thuat | tai_chinh | unknown
    char_len: int
    overlap_prev: int


def chunks_to_jsonl(chunks: list[Chunk]) -> str:
    return "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in chunks)


def outline_to_json(nodes: list[OutlineNode]) -> str:
    return json.dumps([asdict(n) for n in nodes], ensure_ascii=False, indent=2)
