"""Router upload & xử lý tài liệu (OCR/parse đồng bộ cho demo)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from services import artifact_catalog, documents
from services.artifact_classify import validate_artifact

router = APIRouter(prefix="/api/v1/packages", tags=["documents"])


def _detect_kind(filename: str, data: bytes) -> str:
    """Phát hiện loại file: excel hoặc pdf_text/pdf_scan."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return "excel"
    return documents.classify_pdf(data)


def _trung_loai(pkg: models.ProcurementPackage, vendor_id: int | None, artifact_type: str,
                bo_qua_doc_id: int | None = None) -> models.TenderDocument | None:
    """Tài liệu HSDT cùng loại đã tồn tại trong bộ hồ sơ mà nhà thầu này sẽ BỊ CHẤM?

    Phạm vi trùng bám đúng phạm vi pipeline đọc (`_ho_so_cua_vendor`): chấm 1 nhà thầu lấy hồ sơ
    RIÊNG của họ CỘNG tài liệu DÙNG CHUNG (vendor_id NULL). Nên:
    - tài liệu riêng đụng tài liệu riêng của cùng nhà thầu, và đụng cả tài liệu dùng chung;
    - tài liệu dùng chung đụng MỌI tài liệu cùng loại, vì nó gia nhập bộ hồ sơ của mọi nhà thầu.

    Hai file cùng loại nghĩa là hệ thống chấm trên hai nguồn có thể mâu thuẫn mà không ai chọn
    dùng cái nào — tệ hơn nữa, trùng tên file thì cái sau ghi đè cái trước ngay trên đĩa.
    """
    ma = _norm_ma(artifact_type)
    for d in pkg.documents:
        if d.loai != "HSDT" or d.id == bo_qua_doc_id or _norm_ma(d.artifact_type) != ma:
            continue
        if vendor_id is None or d.vendor_id is None or d.vendor_id == vendor_id:
            return d
    return None


def _norm_ma(raw: str | None) -> str:
    return (raw or "").strip().lower()


def _loi_trung(d: models.TenderDocument, artifact_type: str) -> Any:
    nhan = (artifact_catalog.get_artifact(artifact_type) or {}).get("label", artifact_type)
    pham_vi = "dùng chung" if d.vendor_id is None else "của nhà thầu này"
    return fail(f'Loại hồ sơ "{nhan}" đã có file {pham_vi}: {Path(d.file_path).name}. '
                f"Mỗi loại chỉ nộp một file — xóa file cũ rồi tải lại nếu muốn thay.", 409)


@router.post("/{package_id}/documents")
async def upload_document(
    package_id: int,
    loai: str = Form(...),
    vendor_id: int | None = Form(None),
    artifact_type: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload HSMT hoặc HSDT, chạy OCR/parse đồng bộ, lưu kết quả."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    content = await file.read()
    file_kind = _detect_kind(file.filename, content)
    if file_kind == "excel":
        # Pipeline đánh giá hiện thuần vision PDF (experiment/evaluate) -> nhận Excel là nhận rồi
        # bỏ qua âm thầm. Từ chối thẳng cho tới khi có đường xử lý Excel.
        return fail("Chưa hỗ trợ Excel — hãy tải bản PDF của hồ sơ này", 415)
    if loai == "HSDT" and not (artifact_type or "").strip():
        # HSDT không có loại hồ sơ bị _hsdt_files bỏ qua -> tài liệu nằm im trong UI mà không
        # bao giờ được chấm. Bắt khai báo ngay tại nguồn.
        return fail("Thiếu loại hồ sơ — hãy chọn loại hồ sơ cho file HSDT này", 400)
    if loai == "HSDT":
        trung = _trung_loai(pkg, vendor_id, artifact_type or "")
        if trung is not None:
            return _loi_trung(trung, artifact_type or "")
    if loai == "HSMT":
        subdir = "hsmt"
    elif loai == "TBMT":                       # tài liệu gói (scan), không thuộc nhà thầu
        subdir = "tbmt"
    else:
        subdir = f"hsdt/{vendor_id or 0}"
    rel = storage.save_upload(package_id, file.filename, content, subdir)

    doc = models.TenderDocument(
        package_id=package_id,
        loai=loai,
        vendor_id=vendor_id,
        file_path=rel,
        file_kind=file_kind,
        # Ghi loại hồ sơ NGAY khi tạo, ngoài khối OCR: OCR lỗi mà mất loại thì tài liệu bị
        # _hsdt_files bỏ qua âm thầm, tệ hơn nhiều so với chỉ thiếu text.
        artifact_type=(artifact_type or "").strip() or None,
        trang_thai_ocr="dang_xu_ly",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        pages = documents.extract_document(content, file_kind)
        doc.extracted_text = json.dumps(pages, ensure_ascii=False)
        doc.trang_thai_ocr = "hoan_thanh"
        # `pages` rỗng = bản scan (extract_document cố ý không OCR ở bước upload, để vision đọc ảnh
        # lúc chấm). Gọi LLM kiểm loại trên nội dung RỖNG vừa bắt người dùng chờ vô ích, vừa sinh
        # cảnh báo "nghi tải nhầm loại" giả. Không có text thì không có gì để phán -> để None.
        if doc.artifact_type and pages:
            doc.artifact_validation = await validate_artifact(pages, doc.artifact_type)
        else:
            # `default=dict` của cột (models.py) đã gán "{}" ở lần commit đầu tiên (dòng phía
            # trên) — không ghi đè thì "{}" giả một kết quả kiểm loại trong khi không có.
            doc.artifact_validation = None
    except Exception as exc:  # graceful degradation (NFR 5.3)
        doc.trang_thai_ocr = f"loi: {exc}"
    db.commit()
    db.refresh(doc)
    return ok(_doc_out(doc))


@router.get("/{package_id}/documents")
async def list_documents(package_id: int, db: Session = Depends(get_db)):
    """Lấy danh sách tài liệu theo gói thầu."""
    docs = db.scalars(
        select(models.TenderDocument).where(
            models.TenderDocument.package_id == package_id
        )
    ).all()
    return ok([_doc_out(d) for d in docs])


@router.patch("/{package_id}/documents/{doc_id}")
async def update_document_type(package_id: int, doc_id: int, payload: dict[str, Any],
                               db: Session = Depends(get_db)):
    """Đổi LOẠI HỒ SƠ (artifact_type) của tài liệu đã tải — tính lại cảnh báo từ text đã OCR."""
    doc = db.get(models.TenderDocument, doc_id)
    if not doc or doc.package_id != package_id:
        return fail("Không tìm thấy tài liệu", 404)
    pkg = db.get(models.ProcurementPackage, package_id)
    artifact_type = (payload.get("artifact_type") or "").strip()
    if doc.loai == "HSDT" and not artifact_type:
        # Xóa trắng loại = tài liệu biến mất khỏi đánh giá trong khi UI vẫn đếm nó. Muốn bỏ hẳn
        # thì xóa tài liệu, không để nó tồn tại ở trạng thái không chấm được.
        return fail("Không thể bỏ trống loại hồ sơ — chọn loại khác hoặc xóa tài liệu", 400)
    if doc.loai == "HSDT" and artifact_type:
        # Chặn ở upload mà bỏ ngỏ PATCH thì luật vòng qua được bằng hai bước: tải với loại khác
        # rồi đổi loại. Bỏ qua chính tài liệu đang sửa để giữ nguyên loại cũ không bị tự chặn.
        trung = _trung_loai(pkg, doc.vendor_id, artifact_type, bo_qua_doc_id=doc.id)
        if trung is not None:
            return _loi_trung(trung, artifact_type)
    doc.artifact_type = artifact_type or None
    pages = json.loads(doc.extracted_text or "[]")
    # Cùng lý do như lúc upload: file scan có extracted_text="[]" nên không có căn cứ để kiểm.
    doc.artifact_validation = (await validate_artifact(pages, artifact_type)
                               if artifact_type and pages else None)
    db.commit()
    db.refresh(doc)
    return ok(_doc_out(doc))


@router.delete("/{package_id}/documents/{doc_id}")
async def delete_document(package_id: int, doc_id: int, db: Session = Depends(get_db)):
    """Xóa 1 tài liệu (bản ghi + file)."""
    doc = db.get(models.TenderDocument, doc_id)
    if not doc or doc.package_id != package_id:
        return fail("Không tìm thấy tài liệu", 404)
    storage.remove(doc.file_path)
    db.delete(doc)
    db.commit()
    return ok({"deleted": True})


def _doc_out(d: models.TenderDocument) -> dict:
    """Chuyển đổi TenderDocument sang dict response."""
    return {
        "id": d.id,
        "loai": d.loai,
        "vendor_id": d.vendor_id,
        "file_path": d.file_path,
        "file_name": Path(d.file_path).name,
        "file_kind": d.file_kind,
        "trang_thai_ocr": d.trang_thai_ocr,
        "artifact_type": d.artifact_type,
        "artifact_validation": d.artifact_validation,
    }
