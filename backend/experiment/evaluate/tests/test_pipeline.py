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
             ("dkkd.pdf", "dang_ky_kinh_doanh", _pdf("dkkd"))]
    r = await evaluate_hsdt([_crit_ttld()], files, doc="HSDT-A", vision_fn=vision,
                            vendor=VendorContext(ten="Công ty ABC", hinh_thuc="doc_lap"))
    assert r.doc == "HSDT-A"
    assert r.vendor is not None and r.vendor_profile is not None
    assert r.vendor_profile.hinh_thuc == HINH_THUC_DOC_LAP
    assert [h.loai_ho_so for h in r.ho_so_nhan_duoc]          # có danh mục hồ sơ
    # 4 standing check, mỗi cái 1 lần -> 4 TIÊU CHÍ (chữ ký đạt; tên gói SOI vì không pkg; bảo đảm
    # thiếu hồ sơ; phân công liên danh 'không áp dụng'), cộng 1 tiêu chí HSMT.
    from experiment.evaluate.schema import NHOM_PHAT_HIEN
    assert len([c for c in r.criteria if c.nhom == NHOM_PHAT_HIEN]) == 4
    assert r.summary["n_tieu_chi"] == 5


async def test_kiem_tra_thuong_truc_thanh_tieu_chi_nhu_moi_tieu_chi_khac():
    """Kiểm tra thường trực nay là TIÊU CHÍ đầy đủ: vào criteria, vào summary, kéo được 'loại'."""
    from experiment.evaluate.schema import NHOM_PHAT_HIEN

    vision = ScriptedVision({
        "[IN]": {"text": "Công ty ABC", "co_chu_ky": True, "co_dau": True},
        "[RULE:chu_ky_khop_dkkd]": {
            "ket_qua": "không đạt", "nguoi_ky": "A", "dai_dien_phap_luat": "B",
            "nha_thau_don": "Cty ABC", "doanh_nghiep_dkkd": "Cty ABC", "phap_nhan_khop": True,
            "bang_chung": "ký A ≠ đại diện B", "trang": [1]},
    })
    files = [("don.pdf", "don_du_thau", _pdf("đơn")),
             ("dkkd.pdf", "dang_ky_kinh_doanh", _pdf("dkkd"))]
    r = await evaluate_hsdt([], files, doc="A", vision_fn=vision,
                            vendor=VendorContext(ten="Cty ABC"))

    tt = [c for c in r.criteria if c.nhom == NHOM_PHAT_HIEN]
    assert len(tt) == 4                       # 4 kiểm tra -> 4 tiêu chí RIÊNG, không gộp 1 dòng
    assert all(len(c.verdicts) == 1 for c in tt)
    assert all(c.yeu_cau_goc == "" for c in tt)   # không đến từ HSMT

    # KHÔNG tiên quyết: AI đọc sai một verdict mà loại thẳng nhà thầu là rủi ro lớn hơn lợi ích —
    # kết quả vẫn hiện đầy đủ để chuyên gia tự quyết có loại hay không.
    assert not any(c.tien_quyet for c in tt)
    chu_ky = next(c for c in tt if "đại diện pháp luật" in c.ten)
    assert chu_ky.ket_qua == "không đạt" and chu_ky.loai is False

    assert r.summary["n_tieu_chi"] == 4        # vẫn đếm chung
    assert r.summary["n_loai"] == 0            # nhưng không tự loại


async def test_khong_con_field_phat_hien_bo_sung():
    """Bỏ hẳn đường tách riêng — mọi tầng phía sau chỉ còn MỘT danh sách tiêu chí để xử lý."""
    from experiment.evaluate.schema import EvalResult

    assert not hasattr(EvalResult(doc="A"), "phat_hien_bo_sung")


async def test_core_gom_canh_bao_doc_tu_cac_trang():
    """Trang nghi bóc thiếu phải nổi lên tận EvalResult — báo cáo mới nêu được cho chuyên gia."""
    from services.ai_client import AiOutcome

    async def vision(system, prompt, images=(), validate=None, max_tokens=None, seed=None, **kw):
        if images:      # ingest: trả bảng lệch cột ở mọi lần thử
            d = {"text": "STT | Ten | Tien\n1 | May chu | 100\n2 | UPS", "co_chu_ky": False,
                 "co_dau": False}
            return AiOutcome("ok", validate(d) if validate else d, "fake", finish_reason="stop")
        return AiOutcome("error", None, "fake", error="không dùng tới")

    r = await evaluate_hsdt([], [("bg.pdf", "bang_gia", _pdf("scan"))], doc="A", vision_fn=vision)
    assert len(r.canh_bao_doc) == 1
    assert "bg.pdf" in r.canh_bao_doc[0] and "trang 1" in r.canh_bao_doc[0]
    assert "cột" in r.canh_bao_doc[0]


async def test_core_khong_canh_bao_khi_doc_on():
    vision = ScriptedVision({"[IN]": {"text": "đơn dự thầu bình thường"}})
    r = await evaluate_hsdt([], [("don.pdf", "don_du_thau", _pdf("đơn"))], doc="A",
                            vision_fn=vision)
    assert r.canh_bao_doc == []


async def test_core_forwards_cache_to_ingest():
    """Cache xuống tới ingest -> chấm lại nhà thầu không OCR lại (chỗ tốn thời gian nhất)."""
    from experiment.evaluate.ingest import DPI_MAC_DINH, ingest_cache_key

    data = _pdf("đơn")
    cache = {ingest_cache_key(data, DPI_MAC_DINH): [
        {"trang": 1, "text": "đã OCR trước đó", "co_chu_ky": True, "co_dau": False}]}

    class _Cache:
        def get(self, key):
            return cache.get(key)

        def put(self, key, pages):
            cache[key] = pages

    vision = ScriptedVision({})          # KHÔNG kịch bản [IN] -> gọi vision là lỗi ngay
    r = await evaluate_hsdt([], [("don.pdf", "don_du_thau", data)], doc="A",
                            vision_fn=vision, cache=_Cache())
    assert [h.n_trang for h in r.ho_so_nhan_duoc] == [1]
    assert not any("[IN]" in c[0] for c in vision.calls)   # 0 call ingest


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
