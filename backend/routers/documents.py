"""Router upload & xử lý tài liệu (OCR/parse đồng bộ cho demo)."""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from services import documents
from services.artifact_classify import validate_artifact

router = APIRouter(prefix="/api/v1/packages", tags=["documents"])


def _detect_kind(filename: str, data: bytes) -> str:
    """Phát hiện loại file: excel hoặc pdf_text/pdf_scan."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return "excel"
    return documents.classify_pdf(data)


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
    subdir = "hsmt" if loai == "HSMT" else f"hsdt/{vendor_id or 0}"
    rel = storage.save_upload(package_id, file.filename, content, subdir)

    doc = models.TenderDocument(
        package_id=package_id,
        loai=loai,
        vendor_id=vendor_id,
        file_path=rel,
        file_kind=file_kind,
        trang_thai_ocr="dang_xu_ly",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        pages = documents.extract_document(content, file_kind)
        doc.extracted_text = json.dumps(pages, ensure_ascii=False)
        doc.trang_thai_ocr = "hoan_thanh"
        if loai == "HSDT" and artifact_type:
            doc.artifact_type = artifact_type
            doc.artifact_validation = await validate_artifact(pages, artifact_type)
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


def _doc_out(d: models.TenderDocument) -> dict:
    """Chuyển đổi TenderDocument sang dict response."""
    return {
        "id": d.id,
        "loai": d.loai,
        "vendor_id": d.vendor_id,
        "file_path": d.file_path,
        "file_kind": d.file_kind,
        "trang_thai_ocr": d.trang_thai_ocr,
        "artifact_type": d.artifact_type,
        "artifact_validation": d.artifact_validation,
    }
