"""Lõi evaluate_hsdt — 1 đường dùng chung cho CLI lẫn production (chống phân kỳ CLI≠prod)."""
import fitz

from experiment.evaluate.pipeline import evaluate_hsdt
from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleRegistry, RuleSkill
from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, KET_QUA_DAT, KET_QUA_KHONG_AP_DUNG, PackageContext, VendorContext, Verdict,
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
    # 3 standing check, mỗi cái 1 lần: chữ ký đạt; tên gói SOI (không pkg); bảo đảm thiếu hồ sơ
    assert len(r.phat_hien_bo_sung) == 3


async def test_core_passes_pkg_to_standing_rules():
    """Ngữ cảnh gói thầu (tên/mã) phải xuống tới luật standing — luật tên gói thầu cần."""
    seen = {}

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None, pkg=None):
        seen["pkg"] = pkg
        return Verdict(noi_dung_kiem_tra="x", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua=KET_QUA_DAT, bang_chung="", trang=[],
                       do_tin=1.0, ghi_chu="")

    reg = RuleRegistry()
    reg.register(RuleSkill(id="luat_gia", ten="Luật giả", ho_so_can=["don_du_thau"],
                           can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI))
    vision = ScriptedVision({"[IN]": {"text": "đơn"}})
    pkg = PackageContext(ten="Gói thầu ABC", ma_so="G-01")
    await evaluate_hsdt([], [("don.pdf", "don_du_thau", _pdf("đơn"))], doc="A",
                        vision_fn=vision, registry=reg, pkg=pkg)
    assert seen["pkg"] == pkg


async def test_core_runs_gate_like_production_would():
    """Độc lập + tiêu chí TTLĐ -> N/A (gate chạy trong lõi — thứ prod cũ KHÔNG có)."""
    vision = ScriptedVision({"[IN]": {"text": "đơn"}})
    files = [("don.pdf", "don_du_thau", _pdf("đơn"))]      # KHÔNG có file TTLĐ
    r = await evaluate_hsdt([_crit_ttld()], files, doc="A", vision_fn=vision,
                            vendor=VendorContext(ten="ABC", hinh_thuc="doc_lap"))
    assert r.criteria[0].ket_qua == KET_QUA_KHONG_AP_DUNG
