"""Hợp đồng dữ liệu cho bước trích nội dung tiêu chuẩn 4 nhóm (Chương III)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class Block:
    """Một khối nội dung trong một Mục: text (đoạn văn) hoặc table (giữ nguyên rows gốc)."""
    type: str                       # "text" | "table"
    page: list[int]                 # [trang_đầu, trang_cuối]
    text: str | None = None         # cho type="text"
    rows: list[list[str]] | None = None  # cho type="table" — verbatim, KHÔNG parse


@dataclass
class GroupContent:
    group: str                      # hop_le | nang_luc | ky_thuat | tai_chinh
    muc: str                        # tiêu đề Mục
    muc_page: list[int]             # [trang_đầu, trang_cuối]
    is_reference: bool              # Mục chỉ là con trỏ sang section khác?
    ref_target: dict | None         # {"kind": "phan"|"chuong"|"muc", "number": "4"} nếu là tham chiếu
    blocks: list[Block] = field(default_factory=list)


def groups_to_json(doc: str, chuong3_page: list[int], groups: list[GroupContent]) -> str:
    return json.dumps(
        {"doc": doc, "chuong3_page": chuong3_page, "groups": [asdict(g) for g in groups]},
        ensure_ascii=False, indent=2,
    )
