"""Schema đầu ra bước phân rã (experiment-local, output phẳng)."""
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


KET_LUAN_AP_DUNG = "ap_dung"              # điều kiện THOẢ -> vẫn chấm nội dung này
KET_LUAN_KHONG_AP_DUNG = "khong_ap_dung"  # điều kiện KHÔNG thoả -> N/A tất định, khỏi chấm
KET_LUAN_CHUA_QUYET = ""                  # chưa đối chiếu được -> chấm bình thường (fail-safe)


class DieuKienApDung(_Base):
    """Điều kiện kích hoạt theo GIÁ TRỊ — 'chỉ áp dụng khi <đại lượng> <phép> <ngưỡng>'.

    Khác `ap_dung` (chỉ biết hình thức nhà thầu): đây là điều kiện phía HSMT, quyết được NGAY ở
    decompose vì đại lượng đã được tra ở nội dung khác (vd 'Đối với gói thầu có giá trị bảo đảm dự
    thầu nhỏ hơn 50 triệu đồng...' — trong khi HSMT quy định 939.000.000 VND).

    STRUCT điền dai_luong/phep_so_sanh/nguong; bước đối chiếu TẤT ĐỊNH (0 call) sau step search
    điền ket_luan + can_cu. Không đối chiếu được -> ket_luan='' và VẪN CHẤM (không im lặng bỏ sót).
    """
    dai_luong: str = ""       # tên đại lượng cần tra, vd 'giá trị bảo đảm dự thầu'
    phep_so_sanh: str = ""    # < | <= | > | >= | = | !=
    nguong: str = ""          # ngưỡng NGUYÊN VĂN, vd '50 triệu đồng' / '50.000.000 VND'
    ket_luan: str = ""        # (bước đối chiếu) KET_LUAN_* ở trên
    can_cu: str = ""          # (bước đối chiếu) câu giải thích cho báo cáo/chuyên gia


class NoiDungKiemTra(_Base):
    """Một nội dung cần kiểm trên HSDT — đủ để bước chấm thầu đọc & đối chiếu."""
    noi_dung_kiem_tra: str = ""   # Nội dung kiểm tra trên HSDT
    hsdt_kiem_tra: str = ""       # 1 loại HSDT cần xem (từ hsdt_can_kiem_tra của tiêu chí)
    yeu_cau: str = ""             # Yêu cầu cần đáp ứng (theo yeu_cau_goc) — LUÔN có
    can_lam_ro: str = ""          # Thông tin cần làm rõ (chưa rõ trong yeu_cau); '' nếu không
    can_tra_cuu: bool = False     # = (can_lam_ro != '') -> step 3 tra cứu
    thong_tin_bo_sung: str = ""   # (step 3) chuẩn ĐÃ RESOLVE, tự đủ, có quan hệ so sánh
    nguon: str = ""               # (step 3) mã điều khoản nguồn (A-BDL/A-CDNT), cho audit
    can_review: bool = False      # (step 3) True nếu can_tra_cuu mà tra không ra (KHÔNG bịa)
    ap_dung: str = ""             # áp dụng cho ai: ''=mọi nhà thầu | 'lien_danh' | 'doc_lap'
    dieu_kien_ap_dung: DieuKienApDung = DieuKienApDung()  # điều kiện theo giá trị (nếu có)


class ResolvedInfo(_Base):
    """Output step search (resolve 1 need): thông tin bổ sung đã tra + nguồn, hoặc cần review."""
    thong_tin_bo_sung: str = ""
    nguon: str = ""
    can_review: bool = False


class QueryOut(_Base):
    """Output step search (sinh query 1 need)."""
    query: str = ""
    nguon_goi_y: list[Any] = []


class AnchorItem(_Base):
    """Một mốc chung của gói thầu (bảng neo) — chuẩn tương đối tham chiếu tới."""
    ten: str = ""
    gia_tri: str = ""
    nguon: str = ""


class AnchorsModel(_Base):
    neo: list[AnchorItem] = []


class CriterionModel(_Base):
    """Output step structure/resolve — tiêu chí hoàn chỉnh."""
    nhom: str = "hop_le"
    ten: str
    yeu_cau_goc: str = ""
    hsdt_can_kiem_tra: list[Any] = []
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


def validate_anchors(d: dict[str, Any]) -> dict[str, Any]:
    return AnchorsModel(**d).model_dump()


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
