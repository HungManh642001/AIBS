"""Router đề cương chấm: trích từ HSMT, chuyên gia sửa, chốt."""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from responses import ok, fail
from services.hsmt_locator import locate_hsmt_sections
from services.extraction import extract_de_cuong

router = APIRouter(prefix="/api/v1/packages", tags=["de-cuong"])


def _pages(doc: models.TenderDocument) -> list[dict]:
    return json.loads(doc.extracted_text) if doc.extracted_text else []


def _persist(db: Session, package_id: int, criteria: list[dict]) -> None:
    """Xóa đề cương cũ (sub-checks trước, rồi criteria) rồi tạo lại."""
    olds = db.scalars(select(models.EvaluationCriteria).where(
        models.EvaluationCriteria.package_id == package_id)).all()
    old_ids = [c.id for c in olds]
    if old_ids:
        db.query(models.EvaluationSubCheck).filter(
            models.EvaluationSubCheck.criteria_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(models.EvaluationCriteria).filter_by(package_id=package_id).delete()
    for c in criteria:
        row = models.EvaluationCriteria(
            package_id=package_id,
            nhom=c.get("nhom", "hop_le"),
            ten=c.get("ten", ""),
            yeu_cau=c.get("yeu_cau", ""),
            trong_so=float(c.get("trong_so") or 0),
            kieu=c.get("kieu", "pass_fail"),
            required_artifacts=c.get("required_artifacts", []),
        )
        db.add(row)
        db.flush()
        for i, s in enumerate(c.get("sub_checks", [])):
            db.add(models.EvaluationSubCheck(
                criteria_id=row.id,
                ten=s.get("ten", ""),
                check_type=s.get("check_type", ""),
                thong_so=s.get("thong_so", {}),
                required_artifact=s.get("required_artifact", ""),
                thu_tu=i,
                blocking=bool(s.get("blocking", True)),
            ))
    db.commit()


def _read(db: Session, package_id: int) -> dict:
    """Đọc đề cương kèm sub-checks lồng nhau."""
    crits = db.scalars(select(models.EvaluationCriteria).where(
        models.EvaluationCriteria.package_id == package_id)).all()
    out = []
    for c in crits:
        subs = db.scalars(
            select(models.EvaluationSubCheck)
            .where(models.EvaluationSubCheck.criteria_id == c.id)
            .order_by(models.EvaluationSubCheck.thu_tu)
        ).all()
        out.append({
            "id": c.id,
            "nhom": c.nhom,
            "ten": c.ten,
            "yeu_cau": c.yeu_cau,
            "required_artifacts": c.required_artifacts,
            "kieu": c.kieu,
            "trong_so": c.trong_so,
            "sub_checks": [
                {
                    "id": s.id,
                    "ten": s.ten,
                    "check_type": s.check_type,
                    "thong_so": s.thong_so,
                    "required_artifact": s.required_artifact,
                    "blocking": s.blocking,
                }
                for s in subs
            ],
        })
    return {"criteria": out}


@router.post("/{package_id}/de-cuong")
async def extract(package_id: int, db: Session = Depends(get_db)):
    """Trích xuất đề cương từ HSMT bằng AI và lưu vào DB."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    hsmt = next((d for d in pkg.documents if d.loai == "HSMT"), None)
    if not hsmt:
        return fail("Chưa upload HSMT", 400)
    sections = locate_hsmt_sections(_pages(hsmt))
    criteria = await extract_de_cuong(sections)
    _persist(db, package_id, criteria)
    return ok(_read(db, package_id))


@router.get("/{package_id}/de-cuong")
async def get_de_cuong(package_id: int, db: Session = Depends(get_db)):
    """Trả đề cương đã lưu kèm sub-checks."""
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    return ok(_read(db, package_id))


@router.put("/{package_id}/de-cuong")
async def update_de_cuong(package_id: int, payload: dict, db: Session = Depends(get_db)):
    """Cập nhật đề cương theo chỉnh sửa của chuyên gia."""
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    _persist(db, package_id, payload.get("criteria", []))
    return ok(_read(db, package_id))


@router.post("/{package_id}/de-cuong/confirm")
async def confirm_de_cuong(package_id: int, db: Session = Depends(get_db)):
    """Chốt đề cương: chuyển trạng thái gói thầu sang dang_xu_ly."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    pkg.trang_thai = "dang_xu_ly"
    db.commit()
    return ok({"confirmed": True})
