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
        legality = []
        for e in rows:
            do_tins = [vd.do_tin for vd in e.verdicts]
            trang = sorted({t for vd in e.verdicts for t in (vd.trang or [])})
            legality.append({
                "criteria_ten": e.ten,
                "result": e.ket_qua,
                "score": round(sum(do_tins) / len(do_tins), 2) if do_tins else 0.0,
                "evidence": "; ".join(vd.bang_chung for vd in e.verdicts if vd.bang_chung)[:500],
                "page_ref": trang,
                "note": "; ".join(vd.ghi_chu for vd in e.verdicts if vd.ghi_chu),
                "ai_model": "vision",
            })
        fin = financials.get(str(v.id), {})
        price = Decimal(str(fin.get("evaluated_price", 0)))
        so_loi = int(fin.get("so_loi", 0))
        evals[v.id] = {
            "legality": legality,
            "capacity": [],
            "technical": [],
            "financial": {
                "corrected_rows": [],
                "errors": [{}] * so_loi,
                "tong_gia": price,
                "evaluated_price": price,
            },
            "technical_score": 0.0,
            "passed_legality": bool(rows) and all(e.ket_qua != "không đạt" for e in rows),
        }

    return vendor_names, evals


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
            models.HsdtVerdict.ket_qua == "lỗi",
            models.HsdtVerdict.overridden.is_(False),
        )
    )
    if n_err is not None:
        return fail("Còn verdict AI lỗi chưa xử lý — hãy điều chỉnh trước khi xuất báo cáo", 409)

    # Lấy session đánh giá mới nhất để lấy ranking và financials
    # Ghi chú: xếp hạng/tài chính tạm thời trống — sẽ có khi các nhóm ngoài Hợp lệ áp dụng pattern artifact.
    session = db.scalars(
        select(models.EvaluationSession)
        .where(models.EvaluationSession.package_id == package_id)
        .order_by(models.EvaluationSession.id.desc())
    ).first()
    ranking_raw: list[dict] = (
        session.ket_qua_tong_hop.get("ranking", []) if session else []
    )
    financials_map: dict[str, dict] = (
        session.ket_qua_tong_hop.get("financials", {}) if session else {}
    )

    vendor_names, evals = _rebuild_evals(pkg, db, financials_map)
    # Chuyển evaluated_price từ float JSON về Decimal để report builders dùng
    ranking = [
        {**r, "evaluated_price": Decimal(str(r["evaluated_price"]))}
        for r in ranking_raw
    ]

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
