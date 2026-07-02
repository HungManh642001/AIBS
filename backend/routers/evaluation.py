"""Router đánh giá HSDT: pipeline vision (ingest -> route -> đối chiếu -> roll-up) + ghi đè verdict."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

import models
import storage
from database import get_db
from responses import ok, fail
from services.hsdt_pipeline import evaluate_vendor  # tests monkeypatch tên này
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
)

router = APIRouter(prefix="/api/v1", tags=["evaluation"])
log = logging.getLogger("abes.evaluate")


def _criteria_dicts(db: Session, package_id: int) -> list[dict[str, Any]]:
    """RubricCriterion (+noi_dung) -> dict cho evaluate_criterion (order_by thu_tu)."""
    crits = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    return [{
        "nhom": c.nhom, "ten": c.ten, "tien_quyet": c.tien_quyet,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": n.noi_dung_kiem_tra, "hsdt_kiem_tra": n.hsdt_kiem_tra,
             "yeu_cau": n.yeu_cau, "thong_tin_bo_sung": n.thong_tin_bo_sung}
            for n in c.noi_dung],
    } for c in crits]


def _hsdt_files(pkg: models.ProcurementPackage, vendor_id: int) -> list[tuple[str, str, bytes]]:
    """Gom HSDT (pdf) của 1 nhà thầu -> (tên_file, loai_ho_so, bytes). Vision chỉ đọc PDF."""
    out: list[tuple[str, str, bytes]] = []
    for d in pkg.documents:
        if d.loai != "HSDT" or d.vendor_id != vendor_id or not d.artifact_type:
            continue
        if not d.file_kind.startswith("pdf"):
            continue
        out.append((Path(d.file_path).name, d.artifact_type, storage.read_bytes(d.file_path)))
    return out


def _rollup(kqs: set[str]) -> str:
    """Roll-up ket_qua tiêu chí — đồng bộ experiment.evaluate.evaluate_criterion."""
    if KET_QUA_KHONG in kqs:
        return KET_QUA_KHONG
    if kqs & {KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}:
        return KET_QUA_SOI
    if kqs == {KET_QUA_DAT}:
        return KET_QUA_DAT
    return KET_QUA_SOI


def _summary(evals: list[models.HsdtCriterionEval]) -> dict[str, int]:
    def cnt(k: str) -> int:
        return sum(1 for e in evals if e.ket_qua == k)
    return {
        "n_tieu_chi": len(evals), "n_dat": cnt(KET_QUA_DAT), "n_khong_dat": cnt(KET_QUA_KHONG),
        "n_can_lam_ro": cnt(KET_QUA_SOI), "n_loai": sum(1 for e in evals if e.loai),
    }


@router.post("/packages/{package_id}/evaluate")
async def evaluate(package_id: int, db: Session = Depends(get_db)):
    """Chạy pipeline vision đánh giá HSDT từng nhà thầu theo tiêu chí đã chốt; lưu verdict."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crits = _criteria_dicts(db, package_id)
    if not crits:
        return fail("Chưa có tiêu chí đánh giá — hãy bóc & chốt tiêu chí trước", 400)

    # Dọn kết quả cũ của gói (cascade verdicts).
    for e in db.scalars(select(models.HsdtCriterionEval).where(
            models.HsdtCriterionEval.package_id == package_id)).all():
        db.delete(e)
    db.flush()

    vendors_out: list[dict[str, Any]] = []
    for vendor in pkg.vendors:
        files = _hsdt_files(pkg, vendor.id)
        log.info("[eval] gói %s nhà thầu %s: %d file HSDT", package_id, vendor.ten, len(files))
        try:
            result = await evaluate_vendor(crits, files, doc=vendor.ten)
        except Exception as exc:  # no-silent-mock: proxy vision lỗi -> báo rõ, KHÔNG bịa
            log.warning("[eval] gói %s nhà thầu %s: pipeline lỗi: %s", package_id, vendor.ten, exc)
            return fail(f"Đánh giá thất bại: {exc}", 502)
        for i, c in enumerate(result.criteria):
            ev = models.HsdtCriterionEval(
                package_id=package_id, vendor_id=vendor.id, thu_tu=i,
                nhom=c.nhom, ten=c.ten, tien_quyet=c.tien_quyet, ket_qua=c.ket_qua, loai=c.loai)
            db.add(ev)
            db.flush()
            for j, v in enumerate(c.verdicts):
                db.add(models.HsdtVerdict(
                    eval_id=ev.id, thu_tu=j, noi_dung_kiem_tra=v.noi_dung_kiem_tra,
                    hsdt_kiem_tra=v.hsdt_kiem_tra, yeu_cau=v.yeu_cau,
                    thong_tin_bo_sung=v.thong_tin_bo_sung, ket_qua=v.ket_qua,
                    bang_chung=v.bang_chung, trang=v.trang, do_tin=v.do_tin, ghi_chu=v.ghi_chu))
        vendors_out.append({"vendor_id": vendor.id, "ten": vendor.ten, "summary": result.summary})

    pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendors": vendors_out})


@router.get("/packages/{package_id}/results")
async def results(package_id: int, db: Session = Depends(get_db)):
    """Trả verdict đã lưu: mỗi nhà thầu -> tiêu chí -> nội dung (kèm bằng chứng, trang, độ tin)."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    vendors_out = []
    for v in pkg.vendors:
        evals = db.scalars(select(models.HsdtCriterionEval).where(
            models.HsdtCriterionEval.package_id == package_id,
            models.HsdtCriterionEval.vendor_id == v.id)
            .order_by(models.HsdtCriterionEval.thu_tu)).all()
        crit_out = []
        for e in evals:
            crit_out.append({
                "eval_id": e.id, "ten": e.ten, "nhom": e.nhom, "tien_quyet": e.tien_quyet,
                "ket_qua": e.ket_qua, "loai": e.loai,
                "verdicts": [{
                    "id": v2.id, "noi_dung_kiem_tra": v2.noi_dung_kiem_tra,
                    "hsdt_kiem_tra": v2.hsdt_kiem_tra, "yeu_cau": v2.yeu_cau,
                    "thong_tin_bo_sung": v2.thong_tin_bo_sung, "ket_qua": v2.ket_qua,
                    "bang_chung": v2.bang_chung, "trang": v2.trang, "do_tin": v2.do_tin,
                    "ghi_chu": v2.ghi_chu, "overridden": v2.overridden}
                    for v2 in e.verdicts],
            })
        vendors_out.append({"vendor_id": v.id, "ten": v.ten,
                            "summary": _summary(evals), "criteria": crit_out})
    return ok({"vendors": vendors_out})


@router.put("/evaluation/verdict/{verdict_id}/override")
async def override_verdict(verdict_id: int, payload: dict[str, Any], db: Session = Depends(get_db)):
    """Chuyên gia ghi đè verdict 1 nội dung; tính lại roll-up tiêu chí cha; ghi AuditLog."""
    row = db.get(models.HsdtVerdict, verdict_id)
    if not row:
        return fail("Không tìm thấy verdict", 404)
    old = {"ket_qua": row.ket_qua, "ghi_chu": row.ghi_chu}
    if "ket_qua" in payload:
        row.ket_qua = payload["ket_qua"]
    if "ghi_chu" in payload:
        row.ghi_chu = payload["ghi_chu"]
    row.overridden = True

    ev = db.get(models.HsdtCriterionEval, row.eval_id)
    kqs = {v.ket_qua for v in ev.verdicts}
    ev.ket_qua = _rollup(kqs)
    ev.loai = ev.ket_qua == KET_QUA_KHONG and ev.tien_quyet

    db.add(models.AuditLog(
        action="override_verdict", entity_type="hsdt_verdict", entity_id=verdict_id,
        detail=json.dumps({"old": old, "new": payload}, ensure_ascii=False)))
    db.commit()
    db.refresh(row)
    return ok({
        "id": row.id, "ket_qua": row.ket_qua, "ghi_chu": row.ghi_chu, "overridden": row.overridden,
        "criterion": {"eval_id": ev.id, "ket_qua": ev.ket_qua, "loai": ev.loai},
    })
