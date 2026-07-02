"""ORM entities theo PRD §8."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Float, DateTime, ForeignKey, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProcurementPackage(Base):
    __tablename__ = "procurement_package"
    id: Mapped[int] = mapped_column(primary_key=True)
    ma_so: Mapped[str] = mapped_column(String(64), unique=True)
    ten: Mapped[str] = mapped_column(String(512))
    loai: Mapped[str] = mapped_column(String(64), default="hang_hoa")
    gia_tri_uoc_tinh: Mapped[float] = mapped_column(Float, default=0.0)
    trang_thai: Mapped[str] = mapped_column(String(32), default="khoi_tao")
    nguoi_phu_trach: Mapped[str] = mapped_column(String(128), default="")
    ngay_tao: Mapped[datetime] = mapped_column(DateTime, default=_now)

    vendors: Mapped[list[Vendor]] = relationship(back_populates="package", cascade="all, delete-orphan")
    documents: Mapped[list[TenderDocument]] = relationship(back_populates="package", cascade="all, delete-orphan")
    criteria: Mapped[list[EvaluationCriteria]] = relationship(back_populates="package", cascade="all, delete-orphan")


class Vendor(Base):
    __tablename__ = "vendor"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    ten: Mapped[str] = mapped_column(String(512))
    ma_so_thue: Mapped[str] = mapped_column(String(32), default="")
    package: Mapped[ProcurementPackage] = relationship(back_populates="vendors")


class TenderDocument(Base):
    __tablename__ = "tender_document"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    loai: Mapped[str] = mapped_column(String(16))   # HSMT | HSDT
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    file_kind: Mapped[str] = mapped_column(String(16), default="pdf_text")  # pdf_text|pdf_scan|excel
    trang_thai_ocr: Mapped[str] = mapped_column(String(32), default="cho_xu_ly")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    artifact_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_validation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    package: Mapped[ProcurementPackage] = relationship(back_populates="documents")


class EvaluationCriteria(Base):
    __tablename__ = "evaluation_criteria"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    nhom: Mapped[str] = mapped_column(String(16))   # hop_le|nang_luc|ky_thuat|tai_chinh
    ten: Mapped[str] = mapped_column(String(512))
    yeu_cau: Mapped[str] = mapped_column(Text, default="")
    trong_so: Mapped[float] = mapped_column(Float, default=0.0)
    kieu: Mapped[str] = mapped_column(String(16), default="pass_fail")  # pass_fail|score
    required_artifacts: Mapped[list[str]] = mapped_column(JSON, default=list)
    package: Mapped[ProcurementPackage] = relationship(back_populates="criteria")


class EvaluationResult(Base):
    __tablename__ = "evaluation_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    criteria_id: Mapped[int] = mapped_column(ForeignKey("evaluation_criteria.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    ket_qua: Mapped[str] = mapped_column(String(16), default="PARTIAL")  # PASS|FAIL|PARTIAL
    diem_so: Mapped[float] = mapped_column(Float, default=0.0)
    dan_chung: Mapped[str] = mapped_column(Text, default="")
    so_trang: Mapped[list[int]] = mapped_column(JSON, default=list)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    overridden: Mapped[bool] = mapped_column(default=False)


class EvaluationSession(Base):
    __tablename__ = "evaluation_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    trang_thai: Mapped[str] = mapped_column(String(32), default="dang_xu_ly")
    ngay_bat_dau: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ket_qua_tong_hop: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Report(Base):
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    loai: Mapped[str] = mapped_column(String(32))   # tong_hop|tai_chinh|excel...
    file_path: Mapped[str] = mapped_column(String(1024))
    ngay_tao: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column(default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EvaluationSubCheck(Base):
    __tablename__ = "evaluation_sub_check"
    id: Mapped[int] = mapped_column(primary_key=True)
    criteria_id: Mapped[int] = mapped_column(ForeignKey("evaluation_criteria.id"))
    ten: Mapped[str] = mapped_column(String(512))
    check_type: Mapped[str] = mapped_column(String(32))
    thong_so: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    required_artifact: Mapped[str] = mapped_column(String(64), default="")
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    blocking: Mapped[bool] = mapped_column(default=True)


class SubCheckResult(Base):
    __tablename__ = "sub_check_result"
    id: Mapped[int] = mapped_column(primary_key=True)
    sub_check_id: Mapped[int] = mapped_column(ForeignKey("evaluation_sub_check.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    ket_qua: Mapped[str] = mapped_column(String(16), default="PARTIAL")
    evidence: Mapped[str] = mapped_column(Text, default="")
    page_ref: Mapped[list[int]] = mapped_column(JSON, default=list)
    nguon_file: Mapped[str] = mapped_column(String(64), default="")
    ai_model: Mapped[str] = mapped_column(String(64), default="")
    overridden: Mapped[bool] = mapped_column(default=False)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")


# ---- Rubric agentic (decompose pipeline) — bảng riêng cho schema mới ----
class RubricCriterion(Base):
    """Tiêu chí đánh giá do pipeline decompose sinh (thay extract_rubric)."""
    __tablename__ = "rubric_criterion"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    nhom: Mapped[str] = mapped_column(String(16), default="hop_le")
    ten: Mapped[str] = mapped_column(String(512), default="")
    yeu_cau_goc: Mapped[str] = mapped_column(Text, default="")
    hsdt_can_kiem_tra: Mapped[list[str]] = mapped_column(JSON, default=list)
    tien_quyet: Mapped[bool] = mapped_column(default=False)
    loi_ai: Mapped[str] = mapped_column(Text, default="")
    noi_dung: Mapped[list[RubricNoiDung]] = relationship(
        back_populates="criterion", cascade="all, delete-orphan",
        order_by="RubricNoiDung.thu_tu")


class RubricNoiDung(Base):
    """Một nội dung cần kiểm tra của tiêu chí (kèm chuẩn HSMT đã tra)."""
    __tablename__ = "rubric_noi_dung"
    id: Mapped[int] = mapped_column(primary_key=True)
    criterion_id: Mapped[int] = mapped_column(ForeignKey("rubric_criterion.id"))
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    noi_dung_kiem_tra: Mapped[str] = mapped_column(String(512), default="")
    hsdt_kiem_tra: Mapped[str] = mapped_column(String(64), default="")
    yeu_cau: Mapped[str] = mapped_column(Text, default="")
    can_lam_ro: Mapped[str] = mapped_column(Text, default="")
    can_tra_cuu: Mapped[bool] = mapped_column(default=False)
    thong_tin_bo_sung: Mapped[str] = mapped_column(Text, default="")
    nguon: Mapped[str] = mapped_column(String(128), default="")
    can_review: Mapped[bool] = mapped_column(default=False)
    criterion: Mapped[RubricCriterion] = relationship(back_populates="noi_dung")
