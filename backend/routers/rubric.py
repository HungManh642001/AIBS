"""Router tiêu chí đánh giá: bóc từ HSMT bằng pipeline decompose, chuyên gia sửa, chốt."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from services.rubric_pipeline import build_decomposition

router = APIRouter(prefix="/api/v1/packages", tags=["rubric"])


def _persist_decomp(db: Session, package_id: int, decomp: dict) -> None:
    """Xóa tiêu chí cũ của gói (cascade noi_dung) rồi tạo lại từ decomposition dict."""
    olds = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)).all()
    for c in olds:
        db.delete(c)  # cascade xoá noi_dung
    db.flush()

    thu_tu = 0
    for g in decomp.get("groups", []):
        for c in g.get("criteria", []):
            crit = models.RubricCriterion(
                package_id=package_id, thu_tu=thu_tu,
                nhom=c.get("nhom", "hop_le"), ten=c.get("ten", ""),
                yeu_cau_goc=c.get("yeu_cau_goc", ""),
                hsdt_can_kiem_tra=c.get("hsdt_can_kiem_tra", []),
                tien_quyet=bool(c.get("tien_quyet")), loi_ai=c.get("loi_ai", ""),
            )
            db.add(crit)
            db.flush()
            for i, n in enumerate(c.get("noi_dung_can_kiem_tra", [])):
                db.add(models.RubricNoiDung(
                    criterion_id=crit.id, thu_tu=i,
                    noi_dung_kiem_tra=n.get("noi_dung_kiem_tra", ""),
                    hsdt_kiem_tra=n.get("hsdt_kiem_tra", ""),
                    yeu_cau=n.get("yeu_cau", ""), can_lam_ro=n.get("can_lam_ro", ""),
                    can_tra_cuu=bool(n.get("can_tra_cuu")),
                    thong_tin_bo_sung=n.get("thong_tin_bo_sung", ""),
                    nguon=n.get("nguon", ""), can_review=bool(n.get("can_review")),
                ))
            thu_tu += 1
    db.commit()


def _read_decomp(db: Session, package_id: int) -> dict:
    """Đọc tiêu chí + noi_dung_can_kiem_tra lồng nhau."""
    crits = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    out = []
    for c in crits:
        out.append({
            "id": c.id, "nhom": c.nhom, "ten": c.ten, "yeu_cau_goc": c.yeu_cau_goc,
            "hsdt_can_kiem_tra": c.hsdt_can_kiem_tra, "tien_quyet": c.tien_quyet,
            "noi_dung_can_kiem_tra": [
                {"id": n.id, "noi_dung_kiem_tra": n.noi_dung_kiem_tra,
                 "hsdt_kiem_tra": n.hsdt_kiem_tra, "yeu_cau": n.yeu_cau,
                 "can_lam_ro": n.can_lam_ro, "can_tra_cuu": n.can_tra_cuu,
                 "thong_tin_bo_sung": n.thong_tin_bo_sung, "nguon": n.nguon,
                 "can_review": n.can_review}
                for n in c.noi_dung
            ],
        })
    return {"criteria": out}


@router.post("/{package_id}/rubric")
async def extract(package_id: int, db: Session = Depends(get_db)):
    """Bóc tiêu chí từ HSMT bằng pipeline decompose (extract+chunk+index+decompose) và lưu."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    hsmt = next((d for d in pkg.documents if d.loai == "HSMT"), None)
    if not hsmt:
        return fail("Chưa upload HSMT", 400)
    pdf_path = str(storage.abs_path(hsmt.file_path))
    workdir = str(storage.abs_path(f"{package_id}/rubric_work"))
    try:
        decomp = await build_decomposition(pdf_path, workdir)
    except Exception as exc:  # no-silent-mock: pipeline lỗi (proxy tắt...) -> báo rõ
        return fail(f"Bóc tách tiêu chí thất bại: {exc}", 502)
    _persist_decomp(db, package_id, decomp)
    return ok(_read_decomp(db, package_id))


@router.get("/{package_id}/rubric")
async def get_rubric(package_id: int, db: Session = Depends(get_db)):
    """Trả tiêu chí đã lưu kèm noi_dung_can_kiem_tra."""
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    return ok(_read_decomp(db, package_id))


@router.put("/{package_id}/rubric")
async def update_rubric(package_id: int, payload: dict, db: Session = Depends(get_db)):
    """Cập nhật tiêu chí theo chỉnh sửa của chuyên gia."""
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    _persist_decomp(db, package_id, {"groups": [{"criteria": payload.get("criteria", [])}]})
    return ok(_read_decomp(db, package_id))


@router.post("/{package_id}/rubric/confirm")
async def confirm_rubric(package_id: int, db: Session = Depends(get_db)):
    """Chốt tiêu chí: chuyển trạng thái gói thầu sang dang_xu_ly."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    pkg.trang_thai = "dang_xu_ly"
    db.commit()
    return ok({"confirmed": True})
