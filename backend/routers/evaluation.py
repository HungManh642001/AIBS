"""Router đánh giá AI: artifact routing, sub-check results, override."""
from __future__ import annotations
import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from database import get_db
from responses import ok, fail
from services.evaluation.legality import evaluate_legality_routed, compute_completeness

router = APIRouter(prefix="/api/v1", tags=["evaluation"])


def _pages(doc: models.TenderDocument) -> list[dict[str, Any]]:
    """Đọc danh sách trang từ extracted_text (JSON) của tài liệu."""
    if not doc.extracted_text:
        return []
    try:
        return json.loads(doc.extracted_text)
    except (json.JSONDecodeError, TypeError):
        return []


def _artifact_map(pkg: models.ProcurementPackage, vendor_id: int) -> tuple[dict[str, str], set[str]]:
    amap: dict[str, str] = {}
    present: set[str] = set()
    for d in pkg.documents:
        if d.vendor_id != vendor_id or not d.artifact_type:
            continue
        present.add(d.artifact_type)
        pages = json.loads(d.extracted_text) if d.extracted_text else []
        text = "\n".join(p.get("text", "") for p in pages)
        amap[d.artifact_type] = (amap.get(d.artifact_type, "") + "\n" + text).strip()
    return amap, present


@router.post("/packages/{package_id}/evaluate")
async def evaluate(package_id: int, db: Session = Depends(get_db)):
    """Khởi chạy đánh giá AI theo artifact routing — yêu cầu tiêu chí đánh giá đã chốt trước."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crit_rows = list(pkg.criteria)
    if not crit_rows:
        return fail("Chưa có tiêu chí đánh giá — hãy tạo và chốt tiêu chí đánh giá trước", 400)
    # build criterion dicts kèm sub_checks (từ DB)
    crit_dicts: list[dict] = []
    sub_by_crit_ten: dict[str, dict[str, int]] = {}
    for c in crit_rows:
        subs = db.scalars(select(models.EvaluationSubCheck).where(
            models.EvaluationSubCheck.criteria_id == c.id).order_by(models.EvaluationSubCheck.thu_tu)).all()
        sub_by_crit_ten[c.ten] = {s.ten: s.id for s in subs}
        crit_dicts.append({"nhom": c.nhom, "ten": c.ten, "required_artifacts": c.required_artifacts,
                           "sub_checks": [{"ten": s.ten, "check_type": s.check_type, "thong_so": s.thong_so,
                                           "required_artifact": s.required_artifact, "blocking": s.blocking} for s in subs]})
    crit_id_by_ten = {c.ten: c.id for c in crit_rows if c.nhom == "hop_le"}
    # dọn kết quả cũ
    all_sub_ids = [sid for m in sub_by_crit_ten.values() for sid in m.values()]
    if all_sub_ids:
        db.query(models.SubCheckResult).filter(
            models.SubCheckResult.sub_check_id.in_(all_sub_ids)).delete(synchronize_session=False)
    db.query(models.EvaluationResult).filter(
        models.EvaluationResult.criteria_id.in_(list(crit_id_by_ten.values()))).delete(synchronize_session=False)

    vendors_out = []
    for vendor in pkg.vendors:
        amap, present = _artifact_map(pkg, vendor.id)
        max_page = 0
        for d in pkg.documents:
            if d.vendor_id != vendor.id:
                continue
            for p in _pages(d):
                max_page = max(max_page, int(p.get("page", 0)))
        routed = await evaluate_legality_routed(crit_dicts, amap, max_page)
        comp = compute_completeness(crit_dicts, present)
        crit_summ = []
        for r in routed:
            cid = crit_id_by_ten.get(r["criteria_ten"])
            if cid is None:
                continue
            db.add(models.EvaluationResult(criteria_id=cid, vendor_id=vendor.id, ket_qua=r["result"],
                                           diem_so=r["score"], dan_chung="; ".join(s["evidence"] for s in r["sub_results"][:3]),
                                           so_trang=[], ghi_chu="", ai_model="mix"))
            sub_ids = sub_by_crit_ten.get(r["criteria_ten"], {})
            for s in r["sub_results"]:
                sid = sub_ids.get(s["sub_check_ten"])
                if sid is None:
                    continue
                db.add(models.SubCheckResult(sub_check_id=sid, vendor_id=vendor.id, ket_qua=s["result"],
                                             evidence=s["evidence"], page_ref=s["page_ref"], nguon_file=s["nguon_file"],
                                             ai_model=s["ai_model"]))
            crit_summ.append({"criteria_ten": r["criteria_ten"], "result": r["result"], "score": r["score"]})
        vendors_out.append({"vendor_id": vendor.id, "completeness": comp, "criteria": crit_summ})
    pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendors": vendors_out})


@router.get("/packages/{package_id}/results")
async def results(package_id: int, db: Session = Depends(get_db)):
    """Trả về kết quả đánh giá kèm sub_results lồng trong mỗi tiêu chí của mỗi nhà thầu."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crits = list(pkg.criteria)
    vendors_out = []
    for v in pkg.vendors:
        crit_out = []
        for c in crits:
            er = db.scalars(select(models.EvaluationResult).where(
                models.EvaluationResult.criteria_id == c.id,
                models.EvaluationResult.vendor_id == v.id)).first()
            subs = db.scalars(select(models.EvaluationSubCheck).where(
                models.EvaluationSubCheck.criteria_id == c.id)).all()
            sub_ids = [s.id for s in subs]
            srs = db.scalars(select(models.SubCheckResult).where(
                models.SubCheckResult.sub_check_id.in_(sub_ids),
                models.SubCheckResult.vendor_id == v.id)).all() if sub_ids else []
            sub_ten = {s.id: s.ten for s in subs}
            crit_out.append({"criteria_id": c.id, "criteria_ten": c.ten,
                             "result": er.ket_qua if er else None, "score": er.diem_so if er else 0,
                             "sub_results": [{"id": r.id, "sub_check_ten": sub_ten.get(r.sub_check_id, ""),
                                              "result": r.ket_qua, "evidence": r.evidence, "page_ref": r.page_ref,
                                              "nguon_file": r.nguon_file, "ai_model": r.ai_model,
                                              "overridden": r.overridden} for r in srs]})
        crit_list = [{"required_artifacts": c.required_artifacts} for c in crits]
        present = {d.artifact_type for d in pkg.documents if d.vendor_id == v.id and d.artifact_type}
        comp = compute_completeness(crit_list, present)
        vendors_out.append({"vendor_id": v.id, "ten": v.ten, "completeness": comp, "criteria": crit_out})
    return ok({"vendors": vendors_out})


@router.put("/evaluation/{result_id}/override")
async def override(
    result_id: int, payload: dict[str, Any], db: Session = Depends(get_db)
):
    """Chuyên gia ghi đè kết quả AI mức tiêu chí: cập nhật result, ghi AuditLog."""
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


@router.put("/evaluation/sub-check-result/{sub_result_id}/override")
async def override_sub(sub_result_id: int, payload: dict, db: Session = Depends(get_db)):
    """Chuyên gia ghi đè kết quả AI mức sub-check: cập nhật ket_qua, ghi AuditLog."""
    row = db.get(models.SubCheckResult, sub_result_id)
    if not row:
        return fail("Không tìm thấy kết quả sub-check", 404)
    if "ket_qua" in payload:
        row.ket_qua = payload["ket_qua"]
    row.ghi_chu = payload.get("ghi_chu", row.ghi_chu)
    row.overridden = True
    db.add(models.AuditLog(action="override_sub", entity_type="sub_check_result",
                           entity_id=sub_result_id, detail=json.dumps(payload, ensure_ascii=False)))
    db.commit(); db.refresh(row)
    return ok({"id": row.id, "ket_qua": row.ket_qua, "overridden": row.overridden})
