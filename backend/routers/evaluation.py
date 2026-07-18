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
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    VendorContext,
)

router = APIRouter(prefix="/api/v1", tags=["evaluation"])
log = logging.getLogger("abes.evaluate")

_NHOM_PHAT_HIEN = "phat_hien_bo_sung"   # nhóm synthetic: kiểm tra thường trực, NGOÀI roll-up/summary


def _criteria_dicts(db: Session, package_id: int) -> list[dict[str, Any]]:
    """RubricCriterion (+noi_dung) -> dict cho evaluate_criterion (order_by thu_tu)."""
    crits = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    return [{
        "nhom": c.nhom, "ten": c.ten, "tien_quyet": c.tien_quyet,
        "yeu_cau_goc": c.yeu_cau_goc, "hsdt_can_kiem_tra": c.hsdt_can_kiem_tra,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": n.noi_dung_kiem_tra, "hsdt_kiem_tra": n.hsdt_kiem_tra,
             "yeu_cau": n.yeu_cau, "thong_tin_bo_sung": n.thong_tin_bo_sung,
             "nguon": n.nguon, "can_review": n.can_review, "ap_dung": n.ap_dung}
            for n in c.noi_dung],
    } for c in crits]


def _hsdt_files(pkg: models.ProcurementPackage, vendor_id: int) -> list[tuple[str, str, bytes]]:
    """Gom HSDT (pdf) của 1 nhà thầu + tài liệu DÙNG CHUNG (vendor_id NULL, vd webform).

    Tài liệu dùng chung áp cho MỌI nhà thầu; lõi eval tự lọc về đúng dòng nhà thầu trước khi vào
    prompt (loc_dung_chung). Vision chỉ đọc PDF.
    """
    out: list[tuple[str, str, bytes]] = []
    for d in pkg.documents:
        if d.loai != "HSDT" or not d.artifact_type:
            continue
        if d.vendor_id != vendor_id and d.vendor_id is not None:
            continue
        if not d.file_kind.startswith("pdf"):
            continue
        out.append((Path(d.file_path).name, d.artifact_type, storage.read_bytes(d.file_path)))
    return out


def _rollup(kqs: set[str]) -> str:
    """Roll-up ket_qua tiêu chí — đồng bộ experiment.evaluate.evaluate_criterion (N/A trung tính)."""
    xet = kqs - {KET_QUA_KHONG_AP_DUNG}
    if KET_QUA_KHONG in xet:
        return KET_QUA_KHONG
    if xet & {KET_QUA_SOI, KET_QUA_THIEU, KET_QUA_LOI}:
        return KET_QUA_SOI
    if xet == {KET_QUA_DAT}:
        return KET_QUA_DAT
    if kqs and not xet:                 # có verdict nhưng TẤT CẢ N/A
        return KET_QUA_KHONG_AP_DUNG
    return KET_QUA_SOI


def _summary(evals: list[models.HsdtCriterionEval]) -> dict[str, int]:
    """Đếm theo tiêu chí THẬT — LỌC BỎ nhóm phát hiện bổ sung (ngoài checklist HSMT)."""
    tc = [e for e in evals if e.nhom != _NHOM_PHAT_HIEN]

    def cnt(k: str) -> int:
        return sum(1 for e in tc if e.ket_qua == k)
    return {
        "n_tieu_chi": len(tc), "n_dat": cnt(KET_QUA_DAT), "n_khong_dat": cnt(KET_QUA_KHONG),
        "n_can_lam_ro": cnt(KET_QUA_SOI), "n_khong_ap_dung": cnt(KET_QUA_KHONG_AP_DUNG),
        "n_loai": sum(1 for e in tc if e.loai),
    }


async def _eval_and_save_vendor(db: Session, pkg: models.ProcurementPackage,
                                vendor: models.Vendor, crits: list[dict[str, Any]]) -> dict[str, Any]:
    """Đánh giá 1 nhà thầu: dọn kết quả cũ CỦA RIÊNG nhà thầu đó -> chấm -> lưu. Lỗi pipeline -> raise."""
    for e in db.scalars(select(models.HsdtCriterionEval).where(
            models.HsdtCriterionEval.package_id == pkg.id,
            models.HsdtCriterionEval.vendor_id == vendor.id)).all():
        db.delete(e)
    for ve in db.scalars(select(models.HsdtVendorEval).where(
            models.HsdtVendorEval.package_id == pkg.id,
            models.HsdtVendorEval.vendor_id == vendor.id)).all():
        db.delete(ve)
    db.flush()

    files = _hsdt_files(pkg, vendor.id)
    log.info("[eval] gói %s nhà thầu %s: %d file HSDT", pkg.id, vendor.ten, len(files))
    # Tên viết tắt -> alias: webform có lúc ghi tên đầy đủ, có lúc tên tắt -> khớp cả hai.
    aliases = [vendor.ten_viet_tat.strip()] if (vendor.ten_viet_tat or "").strip() else []
    ctx = VendorContext(ten=vendor.ten, aliases=aliases, hinh_thuc=vendor.hinh_thuc or "")
    result = await evaluate_vendor(crits, files, doc=vendor.ten, vendor_ctx=ctx)

    prof = result.vendor_profile
    if prof is not None:
        db.add(models.HsdtVendorEval(
            package_id=pkg.id, vendor_id=vendor.id, hinh_thuc=prof.hinh_thuc, nguon=prof.nguon,
            bang_chung=prof.bang_chung, trang=prof.trang, do_tin=prof.do_tin,
            mau_thuan=prof.mau_thuan, ghi_chu=prof.ghi_chu,
            ho_so_nhan_duoc=[_hsnd(h) for h in result.ho_so_nhan_duoc]))

    for i, c in enumerate(result.criteria):
        _save_eval(db, pkg.id, vendor.id, i, c.nhom, c.ten, c.tien_quyet, c.ket_qua,
                   c.loai, c.yeu_cau_goc, c.verdicts)
    if result.phat_hien_bo_sung:   # kiểm tra thường trực -> nhóm synthetic (ngoài roll-up/summary)
        _save_eval(db, pkg.id, vendor.id, 0, _NHOM_PHAT_HIEN,
                   "Phát hiện của hệ thống (ngoài checklist HSMT)", False,
                   _rollup({v.ket_qua for v in result.phat_hien_bo_sung}), False, "",
                   result.phat_hien_bo_sung)

    return {"vendor_id": vendor.id, "ten": vendor.ten, "summary": result.summary,
            "hinh_thuc": prof.hinh_thuc if prof else "", "mau_thuan": prof.mau_thuan if prof else False,
            "n_phat_hien_bo_sung": len(result.phat_hien_bo_sung)}


@router.post("/packages/{package_id}/vendors/{vendor_id}/evaluate")
async def evaluate_one(package_id: int, vendor_id: int, db: Session = Depends(get_db)):
    """Chạy đánh giá HSDT cho RIÊNG 1 nhà thầu; giữ nguyên kết quả các nhà thầu khác."""
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    vendor = db.get(models.Vendor, vendor_id)
    if not vendor or vendor.package_id != package_id:
        return fail("Không tìm thấy nhà thầu", 404)
    crits = _criteria_dicts(db, package_id)
    if not crits:
        return fail("Chưa có tiêu chí đánh giá — hãy bóc & chốt tiêu chí trước", 400)
    try:
        vendor_out = await _eval_and_save_vendor(db, pkg, vendor, crits)
    except Exception as exc:  # no-silent-mock: proxy vision lỗi -> báo rõ, KHÔNG bịa
        log.warning("[eval] gói %s nhà thầu %s: pipeline lỗi: %s", package_id, vendor.ten, exc)
        return fail(f"Đánh giá thất bại: {exc}", 502)
    pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendor": vendor_out})


@router.post("/packages/{package_id}/evaluate")
async def evaluate(package_id: int, db: Session = Depends(get_db)):
    """Chạy đánh giá HSDT cho TẤT CẢ nhà thầu (tiện lợi chạy hàng loạt).

    Một nhà thầu lỗi KHÔNG hủy cả lô: kết quả các nhà thầu chấm xong vẫn được lưu, nhà thầu lỗi
    liệt kê trong `loi` để chạy lại riêng. Chấm lại cả gói vì 1 proxy timeout là quá đắt.
    """
    pkg = db.get(models.ProcurementPackage, package_id)
    if not pkg:
        return fail("Không tìm thấy gói thầu", 404)
    crits = _criteria_dicts(db, package_id)
    if not crits:
        return fail("Chưa có tiêu chí đánh giá — hãy bóc & chốt tiêu chí trước", 400)
    vendors_out: list[dict[str, Any]] = []
    loi: list[dict[str, Any]] = []
    for vendor in pkg.vendors:
        try:
            vendors_out.append(await _eval_and_save_vendor(db, pkg, vendor, crits))
            db.commit()          # chốt từng nhà thầu -> lỗi sau đó không cuốn theo kết quả trước
        except Exception as exc:  # no-silent-mock: báo rõ nhà thầu nào lỗi, KHÔNG bịa kết quả
            db.rollback()
            log.warning("[eval] gói %s nhà thầu %s: pipeline lỗi: %s", package_id, vendor.ten, exc)
            loi.append({"vendor_id": vendor.id, "ten": vendor.ten, "error": str(exc)})
    if vendors_out:
        pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendors": vendors_out, "loi": loi})


def _hsnd(h) -> dict[str, Any]:
    return {"loai_ho_so": h.loai_ho_so, "files": h.files, "n_trang": h.n_trang}


def _save_eval(db: Session, package_id: int, vendor_id: int, thu_tu: int, nhom: str, ten: str,
               tien_quyet: bool, ket_qua: str, loai: bool, yeu_cau_goc: str, verdicts) -> None:
    """Ghi 1 HsdtCriterionEval + verdict con (đủ chuỗi audit: nguon_hsmt, nguon_doc, yeu_cau_goc)."""
    ev = models.HsdtCriterionEval(
        package_id=package_id, vendor_id=vendor_id, thu_tu=thu_tu, nhom=nhom, ten=ten,
        tien_quyet=tien_quyet, ket_qua=ket_qua, loai=loai, yeu_cau_goc=yeu_cau_goc)
    db.add(ev)
    db.flush()
    for j, v in enumerate(verdicts):
        db.add(models.HsdtVerdict(
            eval_id=ev.id, thu_tu=j, noi_dung_kiem_tra=v.noi_dung_kiem_tra,
            hsdt_kiem_tra=v.hsdt_kiem_tra, yeu_cau=v.yeu_cau,
            thong_tin_bo_sung=v.thong_tin_bo_sung, ket_qua=v.ket_qua, bang_chung=v.bang_chung,
            trang=v.trang, do_tin=v.do_tin, ghi_chu=v.ghi_chu,
            nguon_hsmt=v.nguon_hsmt, nguon_doc=v.nguon_doc))


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
        crit_out = [_eval_out(e) for e in evals if e.nhom != _NHOM_PHAT_HIEN]
        phat_hien = [pv for e in evals if e.nhom == _NHOM_PHAT_HIEN
                     for pv in _eval_out(e)["verdicts"]]
        ve = db.scalar(select(models.HsdtVendorEval).where(
            models.HsdtVendorEval.package_id == package_id,
            models.HsdtVendorEval.vendor_id == v.id))
        vendors_out.append({
            "vendor_id": v.id, "ten": v.ten, "ten_viet_tat": v.ten_viet_tat, "hinh_thuc": v.hinh_thuc,
            "summary": _summary(evals), "criteria": crit_out,
            "phat_hien_bo_sung": phat_hien, "vendor_profile": _profile_out(ve),
            "ho_so_nhan_duoc": ve.ho_so_nhan_duoc if ve else []})
    return ok({"vendors": vendors_out})


def _eval_out(e: models.HsdtCriterionEval) -> dict[str, Any]:
    return {
        "eval_id": e.id, "ten": e.ten, "nhom": e.nhom, "tien_quyet": e.tien_quyet,
        "ket_qua": e.ket_qua, "loai": e.loai, "yeu_cau_goc": e.yeu_cau_goc,
        "verdicts": [{
            "id": v2.id, "noi_dung_kiem_tra": v2.noi_dung_kiem_tra, "hsdt_kiem_tra": v2.hsdt_kiem_tra,
            "yeu_cau": v2.yeu_cau, "thong_tin_bo_sung": v2.thong_tin_bo_sung, "ket_qua": v2.ket_qua,
            "bang_chung": v2.bang_chung, "trang": v2.trang, "do_tin": v2.do_tin,
            "ghi_chu": v2.ghi_chu, "overridden": v2.overridden,
            "nguon_hsmt": v2.nguon_hsmt, "nguon_doc": v2.nguon_doc}
            for v2 in e.verdicts],
    }


def _profile_out(ve: models.HsdtVendorEval | None) -> dict[str, Any] | None:
    if ve is None:
        return None
    return {"hinh_thuc": ve.hinh_thuc, "nguon": ve.nguon, "bang_chung": ve.bang_chung,
            "trang": ve.trang, "do_tin": ve.do_tin, "mau_thuan": ve.mau_thuan, "ghi_chu": ve.ghi_chu}


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
