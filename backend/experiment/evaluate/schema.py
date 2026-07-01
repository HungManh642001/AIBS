"""Schema đánh giá HSDT — verdict đủ để audit (bằng chứng + trang + nguồn chuẩn HSMT)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

KET_QUA_DAT = "đạt"
KET_QUA_KHONG = "không đạt"
KET_QUA_SOI = "cần làm rõ"
KET_QUA_THIEU = "thiếu hồ sơ"
KET_QUA_LOI = "lỗi"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IngestPageModel(_Base):
    """Output vision ingest 1 trang: CHỈ bóc text + cờ thị giác (loại hồ sơ đã biết khi tải file)."""
    text: str = ""
    co_chu_ky: bool = False
    co_dau: bool = False


class EvalVerdictModel(_Base):
    ket_qua: str = KET_QUA_SOI
    bang_chung: str = ""
    trang: list[int] = []
    do_tin: float = 0.0
    ghi_chu: str = ""


def validate_ingest_page(d: dict[str, Any]) -> dict[str, Any]:
    return IngestPageModel(**d).model_dump()


def validate_eval_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return EvalVerdictModel(**d).model_dump()


@dataclass
class PageRecord:
    file: str
    trang: int
    loai_ho_so: str
    text: str
    co_chu_ky: bool = False
    co_dau: bool = False
    image: bytes = b""            # PNG bytes — CHỈ trong RAM, không serialize


@dataclass
class Verdict:
    noi_dung_kiem_tra: str
    hsdt_kiem_tra: str
    yeu_cau: str
    thong_tin_bo_sung: str
    ket_qua: str
    bang_chung: str
    trang: list[int]
    do_tin: float
    ghi_chu: str


@dataclass
class CriterionEval:
    nhom: str
    ten: str
    tien_quyet: bool
    ket_qua: str
    loai: bool
    verdicts: list[Verdict] = field(default_factory=list)


@dataclass
class EvalResult:
    doc: str
    criteria: list[CriterionEval] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        def cnt(k: str) -> int:
            return sum(1 for c in self.criteria if c.ket_qua == k)
        return {
            "n_tieu_chi": len(self.criteria),
            "n_dat": cnt(KET_QUA_DAT),
            "n_khong_dat": cnt(KET_QUA_KHONG),
            "n_can_lam_ro": cnt(KET_QUA_SOI),
            "n_loai": sum(1 for c in self.criteria if c.loai),
        }


def result_to_json(r: EvalResult) -> dict[str, Any]:
    return {
        "doc": r.doc,
        "criteria": [asdict(c) for c in r.criteria],
        "summary": r.summary,
    }
