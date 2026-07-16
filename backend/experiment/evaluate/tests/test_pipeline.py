"""Lõi evaluate_hsdt — 1 đường dùng chung cho CLI lẫn production (chống phân kỳ CLI≠prod)."""
import fitz

from experiment.evaluate.pipeline import evaluate_hsdt
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, KET_QUA_KHONG_AP_DUNG, VendorContext,
)
from experiment.evaluate.vision import ScriptedVision


def _pdf(text):
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


def _crit_ttld():
    return {"nhom": "hop_le", "ten": "Thỏa thuận liên danh", "tien_quyet": True,
            "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh"],
            "noi_dung_can_kiem_tra": [
                {"noi_dung_kiem_tra": "Có thỏa thuận liên danh",
                 "hsdt_kiem_tra": "thoa_thuan_lien_danh", "yeu_cau": "phải có",
                 "thong_tin_bo_sung": "", "nguon": "E-BDL 2.3"}]}


async def test_core_returns_full_result_with_profile_and_standing():
    """Lõi dựng EvalResult ĐỦ: vendor/vendor_profile/ho_so_nhan_duoc/phat_hien_bo_sung."""
    vision = ScriptedVision({
        "[IN]": {"text": "Công ty ABC ...", "co_chu_ky": True, "co_dau": True},
        "[RULE:chu_ky_khop_dkkd]": {"ket_qua": "đạt", "nguoi_ky": "A",
                                    "dai_dien_phap_luat": "A", "bang_chung": "khớp", "trang": [1]},
    })
    files = [("don.pdf", "don_du_thau", _pdf("đơn")),
             ("dkkd.pdf", "tu_cach_phap_ly", _pdf("dkkd"))]
    r = await evaluate_hsdt([_crit_ttld()], files, doc="HSDT-A", vision_fn=vision,
                            vendor=VendorContext(ten="Công ty ABC", hinh_thuc="doc_lap"))
    assert r.doc == "HSDT-A"
    assert r.vendor is not None and r.vendor_profile is not None
    assert r.vendor_profile.hinh_thuc == HINH_THUC_DOC_LAP
    assert [h.loai_ho_so for h in r.ho_so_nhan_duoc]          # có danh mục hồ sơ
    assert len(r.phat_hien_bo_sung) == 1                      # standing chữ ký chạy 1 lần


async def test_core_runs_gate_like_production_would():
    """Độc lập + tiêu chí TTLĐ -> N/A (gate chạy trong lõi — thứ prod cũ KHÔNG có)."""
    vision = ScriptedVision({"[IN]": {"text": "đơn"}})
    files = [("don.pdf", "don_du_thau", _pdf("đơn"))]      # KHÔNG có file TTLĐ
    r = await evaluate_hsdt([_crit_ttld()], files, doc="A", vision_fn=vision,
                            vendor=VendorContext(ten="ABC", hinh_thuc="doc_lap"))
    assert r.criteria[0].ket_qua == KET_QUA_KHONG_AP_DUNG
