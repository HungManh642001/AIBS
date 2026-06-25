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
    pkg: models.ProcurementPackage, db: Session
) -> tuple[dict[int, str], dict[int, dict]]:
    """Tái tạo dicts VendorEvaluation từ EvaluationResult trong DB."""
    criteria = {c.id: c for c in pkg.criteria}
    vendor_names: dict[int, str] = {v.id: v.ten for v in pkg.vendors}
    evals: dict[int, dict] = {}

    for v in pkg.vendors:
        rows = db.scalars(
            select(models.EvaluationResult).where(
                models.EvaluationResult.vendor_id == v.id
            )
        ).all()
        groups: dict[str, list] = {"hop_le": [], "nang_luc": [], "ky_thuat": []}
        for r in rows:
            c = criteria.get(r.criteria_id)
            if not c or c.nhom not in groups:
                continue
            groups[c.nhom].append({
                "criteria_ten": c.ten,
                "result": r.ket_qua,
                "score": r.diem_so,
                "evidence": r.dan_chung,
                "page_ref": r.so_trang,
                "note": r.ghi_chu,
                "ai_model": r.ai_model,
            })
        ky_thuat = groups["ky_thuat"]
        evals[v.id] = {
            "legality": groups["hop_le"],
            "capacity": groups["nang_luc"],
            "technical": ky_thuat,
            "financial": {
                "corrected_rows": [],
                "errors": [],
                "tong_gia": Decimal("0"),
                "evaluated_price": Decimal("0"),
            },
            "technical_score": (
                sum(x["score"] for x in ky_thuat) / len(ky_thuat)
                if ky_thuat
                else 0.0
            ),
            "passed_legality": all(
                x["result"] != "FAIL"
                for x in groups["hop_le"] + groups["nang_luc"]
            ),
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

    vendor_names, evals = _rebuild_evals(pkg, db)

    # Lấy session đánh giá mới nhất để lấy ranking
    session = db.scalars(
        select(models.EvaluationSession)
        .where(models.EvaluationSession.package_id == package_id)
        .order_by(models.EvaluationSession.id.desc())
    ).first()
    ranking_raw: list[dict] = (
        session.ket_qua_tong_hop.get("ranking", []) if session else []
    )
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
