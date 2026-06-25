"""F01 - Router quản lý gói thầu."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from responses import ok, fail
from schemas import PackageCreate, PackageOut, VendorOut

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
