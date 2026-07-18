"""Router sinh & tải báo cáo Word/Excel."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from services import reports
from experiment.evaluate.schema import KET_QUA_DAT, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI

# Hợp lệ = mọi tiêu chí đã KẾT LUẬN ĐƯỢC và không có tiêu chí nào trượt. "cần làm rõ"/"thiếu hồ
# sơ"/"lỗi" nghĩa là chưa đủ căn cứ -> KHÔNG được tính là hợp lệ (trước đây chỉ loại "không đạt",
# nên hồ sơ chưa có bằng chứng nào vẫn ra "hợp lệ").
_KET_QUA_HOP_LE = {KET_QUA_DAT, KET_QUA_KHONG_AP_DUNG}

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _rebuild_evals(
    pkg: models.ProcurementPackage, db: Session,
    financials: dict[str, dict] | None = None,
) -> tuple[dict[int, str], dict[int, dict]]:
    """Tái tạo dicts VendorEvaluation từ verdict HSDT (HsdtCriterionEval) trong DB.

    Phạm vi hiện tại chỉ nhóm hợp lệ; năng lực/kỹ thuật để trống, tài chính là placeholder.
    """
    vendor_names: dict[int, str] = {v.id: v.ten for v in pkg.vendors}
    evals: dict[int, dict] = {}
    if financials is None:
        financials = {}

    for v in pkg.vendors:
        rows = db.scalars(
            select(models.HsdtCriterionEval).where(
                models.HsdtCriterionEval.package_id == pkg.id,
                models.HsdtCriterionEval.vendor_id == v.id,
            ).order_by(models.HsdtCriterionEval.thu_tu)
        ).all()
        # LỌC BỎ nhóm phát hiện bổ sung (ngoài checklist HSMT) khỏi danh sách tiêu chí hợp lệ.
        tieu_chi = [e for e in rows if e.nhom != "phat_hien_bo_sung"]
        legality = [_criteria_row(e) for e in tieu_chi]
        # Phát hiện bổ sung render theo TỪNG verdict (tên nội dung thật, không phải tên eval synthetic).
        phat_hien = [{
            "criteria_ten": vd.noi_dung_kiem_tra, "result": vd.ket_qua, "score": vd.do_tin,
            "evidence": vd.bang_chung, "page_ref": vd.trang or [], "note": vd.ghi_chu}
            for e in rows if e.nhom == "phat_hien_bo_sung" for vd in e.verdicts]
        ve = db.scalar(select(models.HsdtVendorEval).where(
            models.HsdtVendorEval.package_id == pkg.id, models.HsdtVendorEval.vendor_id == v.id))

        fin = financials.get(str(v.id), {})
        price = Decimal(str(fin.get("evaluated_price", 0)))
        so_loi = int(fin.get("so_loi", 0))
        evals[v.id] = {
            "legality": legality,
            "capacity": [],
            "technical": [],
            "phat_hien_bo_sung": phat_hien,
            "hinh_thuc": ve.hinh_thuc if ve else "",
            "hinh_thuc_nguon": ve.nguon if ve else "",
            "mau_thuan": ve.mau_thuan if ve else False,
            "financial": {
                "corrected_rows": [],
                "errors": [{}] * so_loi,
                "tong_gia": price,
                "evaluated_price": price,
            },
            "technical_score": 0.0,
            "passed_legality": bool(tieu_chi) and all(
                e.ket_qua in _KET_QUA_HOP_LE for e in tieu_chi),
        }

    return vendor_names, evals


def _criteria_row(e: models.HsdtCriterionEval) -> dict:
    do_tins = [vd.do_tin for vd in e.verdicts]
    trang = sorted({t for vd in e.verdicts for t in (vd.trang or [])})
    nguon = sorted({vd.nguon_hsmt for vd in e.verdicts if vd.nguon_hsmt})
    evidence = "; ".join(vd.bang_chung for vd in e.verdicts if vd.bang_chung)[:500]
    if nguon:
        evidence = f"[HSMT {', '.join(nguon)}] {evidence}"    # điều khoản nguồn — audit chiều HSMT
    return {
        "criteria_ten": e.ten, "result": e.ket_qua,
        "score": round(sum(do_tins) / len(do_tins), 2) if do_tins else 0.0,
        "evidence": evidence, "page_ref": trang,
        "note": "; ".join(vd.ghi_chu for vd in e.verdicts if vd.ghi_chu), "ai_model": "vision",
    }


@router.post("/packages/{package_id}/reports")
async def generate_report(
    package_id: int,
    loai: str = "word",
    db: Session = Depends(get_db),
) -> dict:
    """Sinh báo cáo Word hoặc Excel từ dữ liệu đánh giá đã lưu."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)

    if loai not in ("word", "excel"):
        return fail("loai phải là 'word' hoặc 'excel'", 422)

    # Chặn xuất khi còn verdict AI lỗi chưa được chuyên gia xử lý.
    n_err = db.scalar(
        select(models.HsdtVerdict).join(
            models.HsdtCriterionEval,
            models.HsdtVerdict.eval_id == models.HsdtCriterionEval.id,
        ).where(
            models.HsdtCriterionEval.package_id == package_id,
            models.HsdtVerdict.ket_qua == KET_QUA_LOI,
            models.HsdtVerdict.overridden.is_(False),
        )
    )
    if n_err is not None:
        return fail("Còn verdict AI lỗi chưa xử lý — hãy điều chỉnh trước khi xuất báo cáo", 409)

    # Phạm vi hiện tại chỉ nhóm hợp lệ -> xếp hạng/tài chính để trống.
    vendor_names, evals = _rebuild_evals(pkg, db, {})
    ranking: list[dict] = []

    out_dir = storage.abs_path(f"{package_id}/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    if loai == "excel":
        path = reports.build_summary_xlsx(
            vendor_names, evals, ranking, out_dir / "bao_cao.xlsx"
        )
    else:
        path = reports.build_summary_docx(
            {"ma_so": pkg.ma_so, "ten": pkg.ten},
            vendor_names,
            evals,
            ranking,
            out_dir / "bao_cao.docx",
        )

    rel = str(path.relative_to(storage.STORAGE_DIR)).replace("\\", "/")
    rep = models.Report(package_id=package_id, loai=loai, file_path=rel)
    db.add(rep)
    db.commit()
    db.refresh(rep)

    return ok({"report_id": rep.id, "loai": loai, "file_path": rel})


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: int, db: Session = Depends(get_db)
) -> FileResponse:
    """Tải về file báo cáo theo report_id."""
    rep = db.get(models.Report, report_id)
    if not rep:
        return fail("Không tìm thấy báo cáo", 404)

    path = storage.abs_path(rep.file_path)
    filename = "bao_cao.xlsx" if rep.loai == "excel" else "bao_cao.docx"
    return FileResponse(str(path), filename=filename)
