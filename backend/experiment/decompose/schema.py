"""Schema đầu ra bước phân rã. Tái dùng CriterionDetailModel của services (read-only)."""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from services.ai_schemas import validate_criterion_detail  # read-only reuse

# Field thêm (ngoài CriterionDetailModel) được giữ qua validate -> đánh dấu cần soi, không bịa.
_EXTRA_KEYS = ("can_review", "loi_ai")


def norm_ten(ten: str) -> str:
    """Chuẩn hoá tên tiêu chí để khử trùng (đ->d trước NFD vì NFD không phân rã đ)."""
    s = (ten or "").lower().strip().replace("đ", "d")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


@dataclass
class Coverage:
    listed_n: int = 0
    final_n: int = 0
    added_by_critique: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class GroupDecomposition:
    group: str
    muc: str
    is_reference: bool = False
    ref_target: dict[str, Any] | None = None
    criteria: list[dict[str, Any]] = field(default_factory=list)
    coverage: Coverage = field(default_factory=Coverage)
    needs_review: list[dict[str, str]] = field(default_factory=list)


@dataclass
class DecomposeResult:
    doc: str
    groups: list[GroupDecomposition] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "n_groups": len(self.groups),
            "n_criteria": sum(len(g.criteria) for g in self.groups),
            "n_needs_review": sum(len(g.needs_review) for g in self.groups),
        }


def validate_criteria(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate từng tiêu chí qua schema production, GIỮ field thêm (can_review/loi_ai)."""
    out: list[dict[str, Any]] = []
    for c in criteria:
        extra = {k: c[k] for k in _EXTRA_KEYS if k in c}
        base = {k: v for k, v in c.items() if k not in _EXTRA_KEYS}
        v = validate_criterion_detail(base)
        v.update(extra)
        out.append(v)
    return out


def result_to_json(r: DecomposeResult) -> dict[str, Any]:
    return {
        "doc": r.doc,
        "groups": [asdict(g) for g in r.groups],
        "summary": r.summary,
    }
