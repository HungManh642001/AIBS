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
    rubric_criteria: Mapped[list[RubricCriterion]] = relationship(cascade="all, delete-orphan")
    hsdt_evals: Mapped[list[HsdtCriterionEval]] = relationship(cascade="all, delete-orphan")
    hsdt_vendor_evals: Mapped[list[HsdtVendorEval]] = relationship(cascade="all, delete-orphan")
    ai_caches: Mapped[list[AiCallCache]] = relationship(cascade="all, delete-orphan")


class Vendor(Base):
    __tablename__ = "vendor"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    ten: Mapped[str] = mapped_column(String(512))                   # tên đầy đủ
    ten_viet_tat: Mapped[str] = mapped_column(String(255), default="")  # khớp webform ghi tên tắt
    hinh_thuc: Mapped[str] = mapped_column(String(32), default="")  # KHAI BÁO: doc_lap|lien_danh|""
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
    # Cache text vision-OCR (bước đắt nhất khi chấm): khóa theo NỘI DUNG file + dpi + prompt,
    # xem experiment/evaluate/ingest.ingest_cache_key. Khóa lệch -> OCR lại.
    ocr_key: Mapped[str] = mapped_column(String(96), default="")
    ocr_pages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    package: Mapped[ProcurementPackage] = relationship(back_populates="documents")


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
    ap_dung: Mapped[str] = mapped_column(String(16), default="")  # ''=mọi | lien_danh | doc_lap
    # Điều kiện áp dụng theo GIÁ TRỊ của gói thầu, decompose đã đối chiếu tất định:
    # {dai_luong, phep_so_sanh, nguong, ket_luan, can_cu} — ket_luan='khong_ap_dung' -> bước chấm
    # trả N/A luôn, khỏi tốn call. Xem experiment/decompose/dieu_kien.py.
    dieu_kien_ap_dung: Mapped[dict] = mapped_column(JSON, default=dict)
    criterion: Mapped[RubricCriterion] = relationship(back_populates="noi_dung")


# ---- Đánh giá HSDT (verdict pipeline vision) — bảng riêng ----
class HsdtCriterionEval(Base):
    """Kết quả đánh giá 1 tiêu chí cho 1 nhà thầu (roll-up từ verdicts)."""
    __tablename__ = "hsdt_criterion_eval"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    nhom: Mapped[str] = mapped_column(String(16), default="hop_le")
    ten: Mapped[str] = mapped_column(String(512), default="")
    ket_qua: Mapped[str] = mapped_column(String(16), default="cần làm rõ")
    yeu_cau_goc: Mapped[str] = mapped_column(Text, default="")  # nguyên văn HSMT — audit chiều HSMT
    verdicts: Mapped[list[HsdtVerdict]] = relationship(
        back_populates="eval", cascade="all, delete-orphan", order_by="HsdtVerdict.thu_tu")


class HsdtVerdict(Base):
    """Verdict 1 nội dung kiểm tra (đối chiếu HSDT vs chuẩn HSMT) — đủ để audit."""
    __tablename__ = "hsdt_verdict"
    id: Mapped[int] = mapped_column(primary_key=True)
    eval_id: Mapped[int] = mapped_column(ForeignKey("hsdt_criterion_eval.id"))
    thu_tu: Mapped[int] = mapped_column(Integer, default=0)
    noi_dung_kiem_tra: Mapped[str] = mapped_column(String(512), default="")
    hsdt_kiem_tra: Mapped[str] = mapped_column(String(64), default="")
    yeu_cau: Mapped[str] = mapped_column(Text, default="")
    thong_tin_bo_sung: Mapped[str] = mapped_column(Text, default="")
    ket_qua: Mapped[str] = mapped_column(String(16), default="cần làm rõ")
    bang_chung: Mapped[str] = mapped_column(Text, default="")
    trang: Mapped[list[int]] = mapped_column(JSON, default=list)
    do_tin: Mapped[float] = mapped_column(Float, default=0.0)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")
    overridden: Mapped[bool] = mapped_column(default=False)
    nguon_hsmt: Mapped[str] = mapped_column(Text, default="")       # mã điều khoản HSMT của chuẩn
    nguon_doc: Mapped[list[str]] = mapped_column(JSON, default=list)  # hồ sơ luật đã đối chiếu
    eval: Mapped[HsdtCriterionEval] = relationship(back_populates="verdicts")


class HsdtVendorEval(Base):
    """Hồ sơ đánh giá cấp NHÀ THẦU (1 dòng/gói×nhà thầu) — hình thức dự thầu đã dò + danh mục hồ sơ."""
    __tablename__ = "hsdt_vendor_eval"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendor.id"))
    hinh_thuc: Mapped[str] = mapped_column(String(32), default="")  # đã DÒ: độc lập|liên danh|""
    nguon: Mapped[str] = mapped_column(String(64), default="")      # căn cứ xác định hình thức
    bang_chung: Mapped[str] = mapped_column(Text, default="")
    trang: Mapped[list[int]] = mapped_column(JSON, default=list)
    do_tin: Mapped[float] = mapped_column(Float, default=0.0)
    mau_thuan: Mapped[bool] = mapped_column(default=False)          # khai báo ≠ hồ sơ (cảnh báo)
    ghi_chu: Mapped[str] = mapped_column(Text, default="")
    ho_so_nhan_duoc: Mapped[list[dict]] = mapped_column(JSON, default=list)


class AiCallCache(Base):
    """Cache kết quả CHẤM theo hash đầu vào — chấm lại cùng hồ sơ + tiêu chí ra y hệt, 0 call.

    Khóa do `experiment/evaluate/cached_vision.khoa_call` băm từ system+prompt+model+tham số sinh;
    gắn thêm gói/nhà thầu để xóa có chọn lọc khi muốn ép AI chấm lại từ đầu.
    """
    __tablename__ = "ai_call_cache"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("procurement_package.id"), index=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendor.id"), nullable=True)
    khoa: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ngay_tao: Mapped[datetime] = mapped_column(DateTime, default=_now)
