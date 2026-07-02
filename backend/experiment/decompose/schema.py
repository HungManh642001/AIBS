"""Schema đầu ra bước phân rã (experiment-local, output phẳng).

Bỏ CriterionDetailModel/sub_checks máy-so-sánh: Qwen3 tự đánh giá thông số, không cần code.
Mỗi tiêu chí: nhom, ten (nhãn ngắn), yeu_cau_goc, hsdt_can_kiem_tra, tien_quyet,
noi_dung_can_kiem_tra[{noi_dung_kiem_tra, hsdt_kiem_tra, yeu_cau, can_lam_ro, thong_tin_bo_sung, nguon, can_review}].
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
    """Một nội dung cần kiểm trên HSDT — đủ để bước chấm thầu đọc & đối chiếu."""
    noi_dung_kiem_tra: str = ""   # Nội dung kiểm tra trên HSDT
    hsdt_kiem_tra: str = ""       # 1 loại HSDT cần xem (từ hsdt_can_kiem_tra của tiêu chí)
    yeu_cau: str = ""             # Yêu cầu cần đáp ứng (theo yeu_cau_goc) — LUÔN có
    can_lam_ro: str = ""          # Thông tin cần làm rõ (chưa rõ trong yeu_cau); '' nếu không
    can_tra_cuu: bool = False     # = (can_lam_ro != '') -> step 3 tra cứu
    thong_tin_bo_sung: str = ""   # (step 3) chuẩn ĐÃ RESOLVE, tự đủ, có quan hệ so sánh
    nguon: str = ""               # (step 3) mã điều khoản nguồn (E-BDL/E-CDNT), cho audit
    can_review: bool = False      # (step 3) True nếu can_tra_cuu mà tra không ra (KHÔNG bịa)


class ResolvedInfo(_Base):
    """Output step search (resolve 1 need): thông tin bổ sung đã tra + nguồn, hoặc cần review."""
    thong_tin_bo_sung: str = ""
    nguon: str = ""
    can_review: bool = False


class QueryOut(_Base):
    """Output step search (sinh query 1 need)."""
    query: str = ""


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


def validate_query(d: dict[str, Any]) -> dict[str, Any]:
    return QueryOut(**d).model_dump()


def validate_resolved_value(d: dict[str, Any]) -> dict[str, Any]:
    return ResolvedInfo(**d).model_dump()


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
