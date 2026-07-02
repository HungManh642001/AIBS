"""F01 - Router quản lý gói thầu."""
from __future__ import annotations
import shutil

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from schemas import PackageCreate, PackageOut, VendorCreate, VendorOut

router = APIRouter(prefix="/api/v1/packages", tags=["packages"])


def _to_out(p: models.ProcurementPackage) -> dict:
    return PackageOut(
        id=p.id, ma_so=p.ma_so, ten=p.ten, loai=p.loai,
        gia_tri_uoc_tinh=p.gia_tri_uoc_tinh, trang_thai=p.trang_thai,
        nguoi_phu_trach=p.nguoi_phu_trach,
        vendors=[VendorOut(id=v.id, ten=v.ten, ma_so_thue=v.ma_so_thue) for v in p.vendors],
        so_tai_lieu=len(p.documents), so_tieu_chi=len(p.criteria),
    ).model_dump()


@router.post("")
async def create_package(payload: PackageCreate, db: Session = Depends(get_db)):
    if db.scalar(select(models.ProcurementPackage).where(
            models.ProcurementPackage.ma_so == payload.ma_so)):
        return fail("Mã gói thầu đã tồn tại", 409)
    pkg = models.ProcurementPackage(
        ma_so=payload.ma_so, ten=payload.ten, loai=payload.loai,
        gia_tri_uoc_tinh=payload.gia_tri_uoc_tinh,
        nguoi_phu_trach=payload.nguoi_phu_trach,
    )
    pkg.vendors = [models.Vendor(ten=name) for name in payload.vendors]
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return ok(_to_out(pkg))


@router.get("")
async def list_packages(trang_thai: str | None = None, q: str | None = None,
                        db: Session = Depends(get_db)):
    stmt = select(models.ProcurementPackage)
    if trang_thai:
        stmt = stmt.where(models.ProcurementPackage.trang_thai == trang_thai)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(models.ProcurementPackage.ten.like(like))
    return ok([_to_out(p) for p in db.scalars(stmt).all()])


@router.get("/{package_id}")
async def get_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    return ok(_to_out(pkg))


@router.post("/{package_id}/vendors")
async def add_vendor(package_id: int, payload: VendorCreate, db: Session = Depends(get_db)):
    """Thêm 1 nhà thầu vào gói thầu; trả gói kèm danh sách nhà thầu đã cập nhật."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    if not payload.ten.strip():
        return fail("Tên nhà thầu không được rỗng", 400)
    db.add(models.Vendor(package_id=package_id, ten=payload.ten.strip(),
                         ma_so_thue=payload.ma_so_thue.strip()))
    db.commit()
    db.refresh(pkg)
    return ok(_to_out(pkg))


@router.delete("/{package_id}")
async def delete_package(package_id: int, db: Session = Depends(get_db)):
    """Xóa gói thầu + toàn bộ dữ liệu phụ thuộc + file đã upload."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    # Dọn bảng cũ theo tiêu chí (FK không có cascade ORM trên package).
    crit_ids = [c.id for c in pkg.criteria]
    if crit_ids:
        sub_ids = [s.id for s in db.scalars(select(models.EvaluationSubCheck).where(
            models.EvaluationSubCheck.criteria_id.in_(crit_ids))).all()]
        if sub_ids:
            db.query(models.SubCheckResult).filter(
                models.SubCheckResult.sub_check_id.in_(sub_ids)).delete(synchronize_session=False)
        db.query(models.EvaluationResult).filter(
            models.EvaluationResult.criteria_id.in_(crit_ids)).delete(synchronize_session=False)
        db.query(models.EvaluationSubCheck).filter(
            models.EvaluationSubCheck.criteria_id.in_(crit_ids)).delete(synchronize_session=False)
    # Tiêu chí rubric mới (FK package_id, ngoài cascade) — cascade noi_dung.
    for c in db.scalars(select(models.RubricCriterion).where(
            models.RubricCriterion.package_id == package_id)).all():
        db.delete(c)
    db.query(models.Report).filter_by(package_id=package_id).delete(synchronize_session=False)
    db.query(models.EvaluationSession).filter_by(package_id=package_id).delete(synchronize_session=False)
    db.delete(pkg)  # cascade vendors/documents/EvaluationCriteria
    db.commit()
    shutil.rmtree(storage.abs_path(str(package_id)), ignore_errors=True)  # dọn file upload + rubric_work
    return ok({"deleted": True})
