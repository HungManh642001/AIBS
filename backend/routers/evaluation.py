"""Router đánh giá AI: trích tiêu chí, chạy đánh giá, kết quả, override."""
from __future__ import annotations
import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from responses import ok, fail
from services.extraction import extract_criteria
from services.evaluation.orchestrator import evaluate_vendor, rank_vendors

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


def _pages(doc: models.TenderDocument) -> list[dict[str, Any]]:
    """Đọc danh sách trang từ extracted_text (JSON) của tài liệu."""
    if not doc.extracted_text:
        return []
    try:
        return json.loads(doc.extracted_text)
    except (json.JSONDecodeError, TypeError):
        return []


@router.post("/packages/{package_id}/evaluate")
async def evaluate(package_id: int, db: Session = Depends(get_db)):
    """Khởi chạy đánh giá AI cho gói thầu: trích tiêu chí, đánh giá nhà thầu, xếp hạng."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)

    hsmt = next((d for d in pkg.documents if d.loai == "HSMT"), None)
    if not hsmt:
        return fail("Chưa upload HSMT", 400)

    # Trích xuất tiêu chí từ HSMT
    criteria_dicts = await extract_criteria(_pages(hsmt))

    # Xóa kết quả đánh giá cũ của tiêu chí cũ TRƯỚC khi xóa tiêu chí
    old_crit_ids = [c.id for c in pkg.criteria]
    if old_crit_ids:
        db.query(models.EvaluationResult).filter(
            models.EvaluationResult.criteria_id.in_(old_crit_ids)
        ).delete(synchronize_session=False)

    # Xóa tiêu chí cũ, tạo lại từ kết quả AI
    db.query(models.EvaluationCriteria).filter_by(package_id=package_id).delete()
    crit_rows: list[models.EvaluationCriteria] = []
    for c in criteria_dicts:
        row = models.EvaluationCriteria(
            package_id=package_id,
            nhom=c.get("nhom", ""),
            ten=c.get("ten", ""),
            yeu_cau=c.get("yeu_cau", ""),
            trong_so=float(c.get("trong_so") or 0),
            kieu=c.get("kieu", "pass_fail"),
        )
        db.add(row)
        crit_rows.append(row)
    db.commit()
    for row in crit_rows:
        db.refresh(row)

    # Map (nhom, tên tiêu chí) -> id để tránh collision khi trùng tên khác nhóm
    crit_by_key: dict[tuple[str, str], int] = {(r.nhom, r.ten): r.id for r in crit_rows}

    # Đánh giá từng nhà thầu
    evals: dict[int, Any] = {}
    for vendor in pkg.vendors:
        vdocs = [d for d in pkg.documents if d.vendor_id == vendor.id]
        hsdt_pages = [p for d in vdocs if d.file_kind != "excel" for p in _pages(d)]
        price_pages = [p for d in vdocs if d.file_kind == "excel" for p in _pages(d)]
        ev = await evaluate_vendor(criteria_dicts, hsdt_pages, price_pages)
        evals[vendor.id] = ev

        # Lưu kết quả từng tiêu chí (map qua (nhom, criteria_ten) để tránh collision)
        for nhom, items in (
            ("hop_le", ev["legality"]),
            ("nang_luc", ev["capacity"]),
            ("ky_thuat", ev["technical"]),
        ):
            for item in items:
                cid = crit_by_key.get((nhom, item["criteria_ten"]))
                if cid is None:
                    continue
                db.add(models.EvaluationResult(
                    criteria_id=cid,
                    vendor_id=vendor.id,
                    ket_qua=item["result"],
                    diem_so=item["score"],
                    dan_chung=item["evidence"],
                    so_trang=item["page_ref"],
                    ghi_chu=item["note"],
                    ai_model=item["ai_model"],
                ))
    db.commit()

    # Tổng hợp xếp hạng, chuyển Decimal -> float để JSON serialize được
    ranking = rank_vendors(evals)
    ranking_json = [
        {**r, "evaluated_price": float(r["evaluated_price"])} for r in ranking
    ]

    # Tạo phiên đánh giá
    session = models.EvaluationSession(
        package_id=package_id,
        trang_thai="cho_review",
        ket_qua_tong_hop={"ranking": ranking_json},
    )
    pkg.trang_thai = "cho_review"
    db.add(session)
    db.commit()
    db.refresh(session)

    return ok({
        "session_id": session.id,
        "ranking": ranking_json,
        "so_tieu_chi": len(crit_rows),
    })


@router.get("/packages/{package_id}/results")
async def results(package_id: int, db: Session = Depends(get_db)):
    """Trả về kết quả đánh giá: tiêu chí, kết quả từng nhà thầu, xếp hạng."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)

    criteria = db.scalars(
        select(models.EvaluationCriteria).where(
            models.EvaluationCriteria.package_id == package_id
        )
    ).all()
    crit_ids = [c.id for c in criteria]

    vendors_out = []
    for v in pkg.vendors:
        rows = (
            db.scalars(
                select(models.EvaluationResult).where(
                    models.EvaluationResult.vendor_id == v.id,
                    models.EvaluationResult.criteria_id.in_(crit_ids),
                )
            ).all()
            if crit_ids
            else []
        )
        vendors_out.append({
            "vendor_id": v.id,
            "ten": v.ten,
            "results": [
                {
                    "id": r.id,
                    "criteria_id": r.criteria_id,
                    "ket_qua": r.ket_qua,
                    "diem_so": r.diem_so,
                    "dan_chung": r.dan_chung,
                    "so_trang": r.so_trang,
                    "ghi_chu": r.ghi_chu,
                    "ai_model": r.ai_model,
                    "overridden": r.overridden,
                }
                for r in rows
            ],
        })

    # Lấy phiên đánh giá mới nhất
    session = db.scalars(
        select(models.EvaluationSession)
        .where(models.EvaluationSession.package_id == package_id)
        .order_by(models.EvaluationSession.id.desc())
    ).first()
    ranking = session.ket_qua_tong_hop.get("ranking", []) if session else []

    return ok({
        "criteria": [
            {
                "id": c.id,
                "nhom": c.nhom,
                "ten": c.ten,
                "yeu_cau": c.yeu_cau,
                "trong_so": c.trong_so,
                "kieu": c.kieu,
            }
            for c in criteria
        ],
        "vendors": vendors_out,
        "ranking": ranking,
    })


@router.put("/evaluation/{result_id}/override")
async def override(
    result_id: int, payload: dict[str, Any], db: Session = Depends(get_db)
):
    """Chuyên gia ghi đè kết quả AI: cập nhật result, ghi AuditLog."""
    row = db.get(models.EvaluationResult, result_id)
    if not row:
        return fail("Không tìm thấy kết quả đánh giá", 404)

    # Lưu giá trị cũ để ghi audit log
    old_values = {"ket_qua": row.ket_qua, "diem_so": row.diem_so}

    if "ket_qua" in payload:
        row.ket_qua = payload["ket_qua"]
    if "diem_so" in payload:
        row.diem_so = float(payload["diem_so"])
    if "ghi_chu" in payload:
        row.ghi_chu = payload["ghi_chu"]
    row.overridden = True

    # Ghi audit log cho thao tác override
    db.add(models.AuditLog(
        action="override",
        entity_type="evaluation_result",
        entity_id=result_id,
        detail=json.dumps(
            {"old": old_values, "new": payload}, ensure_ascii=False
        ),
    ))
    db.commit()
    db.refresh(row)

    return ok({
        "id": row.id,
        "ket_qua": row.ket_qua,
        "diem_so": row.diem_so,
        "overridden": row.overridden,
    })
