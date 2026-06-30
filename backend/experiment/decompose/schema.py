"""Schema đầu ra bước phân rã (experiment-local, output phẳng).

Bỏ CriterionDetailModel/sub_checks máy-so-sánh: Qwen3 tự đánh giá thông số, không cần code.
Mỗi tiêu chí: nhom, ten (nhãn ngắn), yeu_cau_goc, hsdt_can_kiem_tra, tien_quyet,
noi_dung_can_kiem_tra[{ten, gia_tri, nguon hsmt|hsdt, kieu_check, can_review}].
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


def norm_ten(ten: str) -> str:
    """Chuẩn hoá tên tiêu chí để khử trùng (đ->d trước NFD vì NFD không phân rã đ)."""
    s = (ten or "").lower().strip().replace("đ", "d")
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


# ---- schema validate output từng step ----
class CriterionListItemModel(_Base):
    """Output step list/critique: tiêu chí cụ thể + yêu cầu gốc trích từ HSMT."""
    nhom: str = "hop_le"
    ten: str
    yeu_cau_goc: str = ""
    hsdt_can_kiem_tra: list[Any] = []


class CriteriaListModel(_Base):
    criteria: list[CriterionListItemModel] = []


class NoiDungKiemTra(_Base):
    """Một nội dung cần kiểm trên HSDT. gia_tri = giá trị HSMT yêu cầu (đã resolve) | ''."""
    ten: str
    gia_tri: str = ""           # giá trị HSMT yêu cầu, hoặc mô tả điều kiện (với nguon=hsdt)
    nguon: str = "hsmt"         # hsmt = HSMT quy định (cần tra) | hsdt = nhà thầu nộp (đánh giá sau)
    kieu_check: str = ""        # tồn tại | đối chiếu | so sánh ngày ... (nhãn nhẹ, không dispatch code)
    can_review: bool = False    # True nếu nguon=hsmt mà không tra được giá trị (KHÔNG bịa)


class CriterionModel(_Base):
    """Output step structure/resolve — tiêu chí hoàn chỉnh."""
    nhom: str = "hop_le"
    ten: str
    yeu_cau_goc: str = ""
    hsdt_can_kiem_tra: list[Any] = []
    tien_quyet: bool = False
    noi_dung_can_kiem_tra: list[NoiDungKiemTra] = []
    loi_ai: str = ""            # != '' nếu lỗi AI cả tiêu chí


def validate_criteria_list(d: dict[str, Any]) -> dict[str, Any]:
    return CriteriaListModel(**d).model_dump()


def validate_criterion(d: dict[str, Any]) -> dict[str, Any]:
    return CriterionModel(**d).model_dump()


# ---- gom kết quả 1 nhóm / cả tài liệu ----
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


def result_to_json(r: DecomposeResult) -> dict[str, Any]:
    return {
        "doc": r.doc,
        "groups": [asdict(g) for g in r.groups],
        "summary": r.summary,
    }
