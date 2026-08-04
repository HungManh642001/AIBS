"""Router đánh giá HSDT: pipeline vision (ingest -> route -> đối chiếu -> roll-up) + ghi đè verdict."""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
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
from services.ai_cache import DbCallCache, xoa_ai_cache
from services.ocr_cache import DocumentOcrCache, xoa_cache
from services import artifact_catalog
from experiment.evaluate.evaluate import _HO_SO_CHI_LIEN_DANH  # nguồn sự thật duy nhất, xem docstring _lech_hinh_thuc
from experiment.evaluate.ingest import DPI_MAC_DINH, ingest_cache_key
from experiment.evaluate.route import _norm
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_LIEN_DANH,
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_KHONG_AP_DUNG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU,
    PackageContext, VendorContext,
)
from experiment.evaluate.vendor_profile import canon_hinh_thuc

router = APIRouter(prefix="/api/v1", tags=["evaluation"])
log = logging.getLogger("abes.evaluate")

def _criteria_dicts(db: Session, package_id: int) -> list[dict[str, Any]]:
    """RubricCriterion (+noi_dung) -> dict cho evaluate_criterion (order_by thu_tu)."""
    crits = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    return [{
        "nhom": c.nhom, "ten": c.ten,
        "yeu_cau_goc": c.yeu_cau_goc, "hsdt_can_kiem_tra": c.hsdt_can_kiem_tra,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": n.noi_dung_kiem_tra, "hsdt_kiem_tra": n.hsdt_kiem_tra,
             "yeu_cau": n.yeu_cau, "thong_tin_bo_sung": n.thong_tin_bo_sung,
             "nguon": n.nguon, "can_review": n.can_review, "ap_dung": n.ap_dung,
             "dieu_kien_ap_dung": n.dieu_kien_ap_dung or {}}
            for n in c.noi_dung],
    } for c in crits]


def _ho_so_cua_vendor(pkg: models.ProcurementPackage, vendor_id: int) -> list[models.TenderDocument]:
    """HSDT của 1 nhà thầu + tài liệu DÙNG CHUNG (vendor_id NULL, vd webform).

    Tài liệu dùng chung áp cho MỌI nhà thầu; lõi eval tự lọc về đúng dòng nhà thầu trước khi vào
    prompt (loc_dung_chung).
    """
    return [d for d in pkg.documents
            if d.loai == "HSDT" and d.vendor_id in (vendor_id, None)]


def _thieu_loai_ho_so(pkg: models.ProcurementPackage, vendor_id: int) -> list[str]:
    """Tên các file HSDT chưa gán loại hồ sơ — không chấm được, phải báo thay vì bỏ qua."""
    return [Path(d.file_path).name
            for d in _ho_so_cua_vendor(pkg, vendor_id) if not d.artifact_type]


def _ma_catalog(raw: Any) -> str:
    """Ép 1 mã loại hồ sơ về code catalog; không tra được -> giữ nguyên mã gốc.

    `hsdt_can_kiem_tra` / `hsdt_kiem_tra` do LLM sinh nên hay là alias ('ket_qua_mo_thau',
    'bao_lanh_du_thau'), trong khi `ho_so_nhan_duoc.loai_ho_so` luôn là mã chuẩn (chọn từ dropdown
    catalog). Không quy về một mối thì `la_dung_chung` trượt (quy kết nhà thầu chưa nộp tài liệu
    của BÊN MỜI THẦU), phép so tập sinh "chưa nộp" giả, và mã thô lọt ra UI vì không tra được nhãn.
    Giữ mã gốc khi tra hụt để loại hồ sơ lạ vẫn hiện ra chứ không biến mất im lặng (no-silent-mock).
    """
    s = str(raw or "").strip()
    return artifact_catalog.resolve_code(s) or s


def _ho_so_chua_nop(crits: Sequence[models.RubricCriterion],
                    ve: models.HsdtVendorEval | None) -> list[dict[str, Any]]:
    """Loại hồ sơ HSMT đòi mà nhà thầu CHƯA NỘP, kèm tiêu chí bị ảnh hưởng.

    CHƯA CHẤM thì im lặng. `ve is None` nghĩa là nhà thầu chưa được chấm lần nào (bình thường:
    có endpoint chấm riêng từng nhà thầu), nên KHÔNG có căn cứ nào về hồ sơ đã nhận — hồ sơ có thể
    đã tải lên đủ. Khác hẳn ca `ve` tồn tại mà `ho_so_nhan_duoc` rỗng: ở đó đã chấm rồi, rỗng là
    một phát hiện thật (nhà thầu không nộp gì) và vẫn phải báo.

    Khác `_thieu_loai_ho_so` (file đã tải nhưng chưa gán loại) — đây là loại hồ sơ hoàn toàn vắng
    mặt. Trừ hai nhóm khỏi tập yêu cầu:

    - Tài liệu DÙNG CHUNG (webform = kết quả mở thầu) do bên mời thầu công bố cho cả gói, không
      phải thứ nhà thầu nộp — báo thiếu là quy kết sai.
    - Loại mà MỌI nội dung trỏ tới nó đều lệch hình thức của nhà thầu. "Lệch" xét CẢ HAI tín hiệu
      mà `_gate_khong_ap_dung` xét (KHÔNG cài lại phép gate, chỉ đọc lại đúng 2 tín hiệu đó):
      trường `ap_dung` do decompose gán, VÀ loại hồ sơ nằm trong `_HO_SO_CHI_LIEN_DANH` (hiển
      nhiên chỉ-liên-danh, vd `thoa_thuan_lien_danh`). Cần tín hiệu thứ hai vì `ap_dung` do LLM
      gán lúc decompose nên có thể bị bỏ trống — nếu banner chỉ dựa `ap_dung`, một tiêu chí bị
      quên gán cờ sẽ khiến banner báo "chưa nộp" ngay trong khi verdict trên cùng trang đã "không
      áp dụng", hai tín hiệu mâu thuẫn nhau trước mắt chuyên gia.

    Không nội dung nào trỏ tới loại đó (`nds` rỗng — loại chỉ đóng vai TÀI LIỆU ĐỐI CHIẾU) thì lùi
    lên xét CẢ TIÊU CHÍ: mọi nội dung của tiêu chí đều lệch hình thức -> tiêu chí ấy không đóng góp
    gì cho nhà thầu này (verdict của nó là "không áp dụng"), nên nó cũng không được kéo tài liệu
    đối chiếu vào banner. Tiêu chí trộn nội dung chung với nội dung điều kiện liên danh thì VẪN
    giữ loại — không được giấu phát hiện thật.

    Chưa dò được hình thức -> KHÔNG trừ theo hình thức (fail-safe: thà báo thừa còn hơn giấu mất
    một loại hồ sơ thật sự thiếu).

    So tập sau khi ép mã về catalog (`_ma_catalog`) rồi `_norm` như lõi eval vẫn dùng — cùng một
    quy tắc khớp, không sinh nguồn sự thật thứ hai. Ép mã cũng gộp các alias của cùng một loại
    thành MỘT dòng banner.
    """
    if ve is None:
        return []
    hinh_thuc = ve.hinh_thuc or ""
    da_nhan = {_norm(_ma_catalog(h.get("loai_ho_so", ""))) for h in (ve.ho_so_nhan_duoc or [])}

    # mã catalog -> {"tieu_chi": [...], "chi_hinh_thuc_khac": bool}
    can: dict[str, dict[str, Any]] = {}
    for c in crits:
        noi_dung = list(c.noi_dung)
        for raw in (c.hsdt_can_kiem_tra or []):
            ma = _ma_catalog(raw)
            if not ma or artifact_catalog.la_dung_chung(_norm(ma)):
                continue
            muc = can.setdefault(ma, {"tieu_chi": [], "chi_hinh_thuc_khac": True})
            if c.ten not in muc["tieu_chi"]:
                muc["tieu_chi"].append(c.ten)
            # Loại này còn "áp dụng" nếu có ÍT NHẤT MỘT nội dung không bị lệch hình thức.
            nds = [n for n in noi_dung if _norm(_ma_catalog(n.hsdt_kiem_tra)) == _norm(ma)]
            xet = nds or noi_dung        # nds rỗng -> lùi lên xét cả tiêu chí (tài liệu đối chiếu)
            if not hinh_thuc or not xet:
                muc["chi_hinh_thuc_khac"] = False
            elif any(not _lech_hinh_thuc(n, hinh_thuc) for n in xet):
                muc["chi_hinh_thuc_khac"] = False

    return [{"loai_ho_so": ma, "tieu_chi": muc["tieu_chi"]}
            for ma, muc in can.items()
            if _norm(ma) not in da_nhan and not muc["chi_hinh_thuc_khac"]]


def _lech_hinh_thuc(nd: models.RubricNoiDung, hinh_thuc: str) -> bool:
    """Nội dung chỉ áp dụng một hình thức, mà nhà thầu thuộc hình thức KHÁC?

    Cùng 2 tín hiệu mà `_gate_khong_ap_dung` (`experiment/evaluate/evaluate.py`) dùng để phát
    verdict "không áp dụng": `ap_dung` (tường minh, do decompose gán) VÀ `hsdt_kiem_tra` nằm
    trong `_HO_SO_CHI_LIEN_DANH` (ngầm định, hiển nhiên chỉ-liên-danh dù `ap_dung` bị bỏ trống).
    Chỉ xét `ap_dung` thì đúng logic decompose lý tưởng nhưng sai thực tế: `ap_dung` do LLM gán,
    thiếu sót ở đó là chuyện thường, và banner phải luôn khớp với verdict lõi eval đã phát ra.
    """
    ap = canon_hinh_thuc(nd.ap_dung or "")
    chi_lien_danh = ap == HINH_THUC_LIEN_DANH or _norm(nd.hsdt_kiem_tra) in _HO_SO_CHI_LIEN_DANH
    chi_doc_lap = ap == HINH_THUC_DOC_LAP
    return ((hinh_thuc == HINH_THUC_DOC_LAP and chi_lien_danh)
            or (hinh_thuc == HINH_THUC_LIEN_DANH and chi_doc_lap))


def _hsdt_files(pkg: models.ProcurementPackage,
                vendor_id: int) -> tuple[list[tuple[str, str, bytes]], dict[str, int]]:
    """Gom hồ sơ đã sẵn sàng chấm + bản đồ {khóa cache OCR: doc_id}.

    Vision chỉ đọc PDF (Excel bị chặn từ bước upload). Băm khóa NGAY tại đây vì đây là chỗ duy
    nhất có cả bytes lẫn id tài liệu — adapter cache khỏi phải đọc lại file.
    """
    files: list[tuple[str, str, bytes]] = []
    khoa: dict[str, int] = {}
    for d in _ho_so_cua_vendor(pkg, vendor_id):
        if not (d.artifact_type and d.file_kind.startswith("pdf")):
            continue
        data = storage.read_bytes(d.file_path)
        files.append((Path(d.file_path).name, d.artifact_type, data))
        khoa[ingest_cache_key(data, DPI_MAC_DINH)] = d.id
    return files, khoa


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
    """Đếm MỌI tiêu chí — kiểm tra thường trực của hệ thống có trọng số ngang tiêu chí HSMT.

    `n_thieu_ho_so` là một LÁT CẮT ĐỘC LẬP trên cùng tập tiêu chí, KHÔNG phải tập con của
    `n_can_lam_ro`: một tiêu chí có thể có verdict 'không đạt' VÀ verdict 'thiếu hồ sơ' cùng lúc
    (vd nội dung A sai, nội dung B không nộp) — khi đó roll-up ưu tiên 'không đạt' (xem `_rollup`,
    KET_QUA_KHONG đứng trước {SOI, THIEU, LOI}) nên tiêu chí rơi vào `n_khong_dat`, KHÔNG vào
    `n_can_lam_ro`. Nếu lọc `n_thieu_ho_so` theo `e.ket_qua == KET_QUA_SOI` để ép nó thành con của
    `n_can_lam_ro`, việc thiếu tài liệu ở đúng những tiêu chí đã có vấn đề khác sẽ bị giấu đi —
    mà đó lại là chỗ chuyên gia cần biết nhất. Vì là lát cắt độc lập, `n_thieu_ho_so` KHÔNG tham
    gia đẳng thức n_tieu_chi = n_dat + n_khong_dat + n_can_lam_ro + n_khong_ap_dung (4 ô đó vẫn
    đủ và loại trừ lẫn nhau bình thường). Đếm theo TIÊU CHÍ (không theo verdict) để cùng đơn vị
    với các ô còn lại.
    """
    tc = list(evals)

    def cnt(k: str) -> int:
        return sum(1 for e in tc if e.ket_qua == k)
    return {
        "n_tieu_chi": len(tc), "n_dat": cnt(KET_QUA_DAT), "n_khong_dat": cnt(KET_QUA_KHONG),
        "n_can_lam_ro": cnt(KET_QUA_SOI), "n_khong_ap_dung": cnt(KET_QUA_KHONG_AP_DUNG),
        "n_thieu_ho_so": sum(1 for e in tc
                             if any(v.ket_qua == KET_QUA_THIEU for v in e.verdicts)),
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

    files, khoa_ocr = _hsdt_files(pkg, vendor.id)
    log.info("[eval] gói %s nhà thầu %s: %d file HSDT", pkg.id, vendor.ten, len(files))
    # Tên viết tắt -> alias: webform có lúc ghi tên đầy đủ, có lúc tên tắt -> khớp cả hai.
    aliases = [vendor.ten_viet_tat.strip()] if (vendor.ten_viet_tat or "").strip() else []
    ctx = VendorContext(ten=vendor.ten, aliases=aliases, hinh_thuc=vendor.hinh_thuc or "")
    pkg_ctx = PackageContext(ten=pkg.ten, ma_so=pkg.ma_so or "")
    # Hai lớp cache: OCR (text đã bóc) + kết quả chấm. Hồ sơ và tiêu chí không đổi -> chấm lại ra
    # Y HỆT lần trước và gần như 0 call; muốn AI làm lại thì xóa cache (DELETE .../cache).
    result = await evaluate_vendor(crits, files, doc=vendor.ten, vendor_ctx=ctx, pkg_ctx=pkg_ctx,
                                   cache=DocumentOcrCache(db, khoa_ocr),
                                   call_cache=DbCallCache(db, pkg.id, vendor.id))

    prof = result.vendor_profile
    if prof is not None:
        db.add(models.HsdtVendorEval(
            package_id=pkg.id, vendor_id=vendor.id, hinh_thuc=prof.hinh_thuc, nguon=prof.nguon,
            bang_chung=prof.bang_chung, trang=prof.trang, do_tin=prof.do_tin,
            mau_thuan=prof.mau_thuan, ghi_chu=prof.ghi_chu,
            ho_so_nhan_duoc=[_hsnd(h) for h in result.ho_so_nhan_duoc]))

    for i, c in enumerate(result.criteria):
        _save_eval(db, pkg.id, vendor.id, i, c.nhom, c.ten, c.ket_qua, c.yeu_cau_goc,
                   c.verdicts)

    return {"vendor_id": vendor.id, "ten": vendor.ten, "summary": result.summary,
            "hinh_thuc": prof.hinh_thuc if prof else "",
            "mau_thuan": prof.mau_thuan if prof else False}


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
    thieu = _thieu_loai_ho_so(pkg, vendor.id)
    if thieu:
        return fail(f"Chưa gán loại hồ sơ cho: {', '.join(thieu)} — "
                    "gán loại rồi chạy lại, nếu không các file này sẽ không được chấm", 400)
    try:
        vendor_out = await _eval_and_save_vendor(db, pkg, vendor, crits)
    except Exception as exc:  # no-silent-mock: proxy vision lỗi -> báo rõ, KHÔNG bịa
        log.warning("[eval] gói %s nhà thầu %s: pipeline lỗi: %s", package_id, vendor.ten, exc)
        return fail(f"Đánh giá thất bại: {exc}", 502)
    pkg.trang_thai = "cho_review"
    db.commit()
    return ok({"vendor": vendor_out})


@router.delete("/packages/{package_id}/cache")
async def clear_cache(package_id: int, loai: str = "tat_ca", vendor_id: int | None = None,
                      doc_id: int | None = None, db: Session = Depends(get_db)):
    """Xóa cache để ép AI làm lại từ đầu (nghi đọc/chấm sai, vừa đổi model...).

    `loai`: 'ocr' (text đã bóc) | 'ai' (kết quả chấm) | 'tat_ca' (mặc định). Thu hẹp phạm vi bằng
    `vendor_id` / `doc_id` (doc_id chỉ áp cho cache OCR).

    KHÔNG cần gọi khi tài liệu đổi nội dung hoặc tiêu chí đổi: cả hai khóa cache đều băm từ đầu
    vào nên tự hết hiệu lực.
    """
    if not db.get(models.ProcurementPackage, package_id):
        return fail("Không tìm thấy gói thầu", 404)
    n_ocr = n_ai = 0
    if loai in ("ocr", "tat_ca"):
        n_ocr = xoa_cache(db, package_id, vendor_id=vendor_id, doc_id=doc_id)
    if loai in ("ai", "tat_ca"):
        n_ai = xoa_ai_cache(db, package_id, vendor_id=vendor_id)
    return ok({"n_tai_lieu": n_ocr, "n_ket_qua_cham": n_ai})


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
        thieu = _thieu_loai_ho_so(pkg, vendor.id)
        if thieu:
            loi.append({"vendor_id": vendor.id, "ten": vendor.ten,
                        "error": f"Chưa gán loại hồ sơ cho: {', '.join(thieu)}"})
            continue
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
               ket_qua: str, yeu_cau_goc: str, verdicts) -> None:
    """Ghi 1 HsdtCriterionEval + verdict con (đủ chuỗi audit: nguon_hsmt, nguon_doc, yeu_cau_goc)."""
    ev = models.HsdtCriterionEval(
        package_id=package_id, vendor_id=vendor_id, thu_tu=thu_tu, nhom=nhom, ten=ten,
        ket_qua=ket_qua, yeu_cau_goc=yeu_cau_goc)
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
    # Rubric là CHUNG cả gói -> lấy một lần cho mọi nhà thầu, thay vì truy vấn lại + lazy-load
    # `.noi_dung` cho từng nhà thầu.
    crits: Sequence[models.RubricCriterion] = db.scalars(select(models.RubricCriterion).where(
        models.RubricCriterion.package_id == package_id)
        .order_by(models.RubricCriterion.thu_tu)).all()
    vendors_out = []
    for v in pkg.vendors:
        evals = db.scalars(select(models.HsdtCriterionEval).where(
            models.HsdtCriterionEval.package_id == package_id,
            models.HsdtCriterionEval.vendor_id == v.id)
            .order_by(models.HsdtCriterionEval.thu_tu)).all()
        crit_out = [_eval_out(e) for e in evals]
        ve = db.scalar(select(models.HsdtVendorEval).where(
            models.HsdtVendorEval.package_id == package_id,
            models.HsdtVendorEval.vendor_id == v.id))
        vendors_out.append({
            "vendor_id": v.id, "ten": v.ten, "ten_viet_tat": v.ten_viet_tat, "hinh_thuc": v.hinh_thuc,
            "summary": _summary(evals), "criteria": crit_out,
            "vendor_profile": _profile_out(ve),
            "ho_so_nhan_duoc": ve.ho_so_nhan_duoc if ve else [],
            "ho_so_chua_nop": _ho_so_chua_nop(crits, ve)})
    return ok({"vendors": vendors_out})


def _eval_out(e: models.HsdtCriterionEval) -> dict[str, Any]:
    return {
        "eval_id": e.id, "ten": e.ten, "nhom": e.nhom,
        "ket_qua": e.ket_qua, "yeu_cau_goc": e.yeu_cau_goc,
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

    db.add(models.AuditLog(
        action="override_verdict", entity_type="hsdt_verdict", entity_id=verdict_id,
        detail=json.dumps({"old": old, "new": payload}, ensure_ascii=False)))
    db.commit()
    db.refresh(row)
    return ok({
        "id": row.id, "ket_qua": row.ket_qua, "ghi_chu": row.ghi_chu, "overridden": row.overridden,
        "criterion": {"eval_id": ev.id, "ket_qua": ev.ket_qua},
    })
