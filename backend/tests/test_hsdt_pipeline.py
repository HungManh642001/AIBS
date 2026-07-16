"""Test service đánh giá HSDT (offline, ScriptedVision — không đụng proxy vision thật)."""
import fitz

from experiment.evaluate.prompts import SYS_EVAL, SYS_INGEST
from experiment.evaluate.vision import ScriptedVision
from services.hsdt_pipeline import evaluate_vendor


def _pdf(text: str) -> bytes:
    d = fitz.open()
    d.new_page().insert_htmlbox(fitz.Rect(72, 72, 500, 200), f"<p>{text}</p>")
    return d.tobytes()


async def test_evaluate_vendor_dat(monkeypatch):
    vision = ScriptedVision({
        SYS_INGEST: {"text": "Đơn dự thầu có chữ ký và đóng dấu", "co_chu_ky": True, "co_dau": True},
        SYS_EVAL: {"ket_qua": "đạt", "bang_chung": "Có chữ ký, đóng dấu hợp lệ",
                   "trang": [1], "do_tin": 0.9},
    })
    criteria = [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": True,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Chữ ký & con dấu", "hsdt_kiem_tra": "don_du_thau",
             "yeu_cau": "có chữ ký hợp lệ", "thong_tin_bo_sung": "theo mẫu E-HSMT"}],
    }]
    files = [("don.pdf", "don_du_thau", _pdf("Đơn dự thầu"))]

    result = await evaluate_vendor(criteria, files, doc="Công ty A", vision_fn=vision)

    assert len(result.criteria) == 1
    c = result.criteria[0]
    assert c.ket_qua == "đạt" and c.loai is False
    assert c.verdicts[0].bang_chung and c.verdicts[0].trang == [1]
    assert result.summary["n_dat"] == 1


async def test_evaluate_vendor_runs_gate_in_production():
    """Prod giờ chạy gate hình thức: độc lập + tiêu chí TTLĐ -> 'không áp dụng' (khác hành vi cũ).

    Trước đây evaluate_vendor gọi evaluate_criterion không profile -> tiêu chí này ra 'thiếu hồ sơ'
    -> 'cần làm rõ'. Nay lõi dùng chung dò hình thức + gate.
    """
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG, VendorContext

    vision = ScriptedVision({SYS_INGEST: {"text": "Đơn dự thầu"}})
    criteria = [{
        "nhom": "hop_le", "ten": "Thỏa thuận liên danh", "tien_quyet": True,
        "hsdt_can_kiem_tra": ["thoa_thuan_lien_danh"],
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Có thỏa thuận liên danh", "hsdt_kiem_tra": "thoa_thuan_lien_danh",
             "yeu_cau": "phải có", "thong_tin_bo_sung": ""}]}]
    files = [("don.pdf", "don_du_thau", _pdf("Đơn dự thầu"))]

    result = await evaluate_vendor(criteria, files, doc="Cty A", vision_fn=vision,
                                   vendor_ctx=VendorContext(ten="Cty A", hinh_thuc="doc_lap"))
    assert result.criteria[0].ket_qua == KET_QUA_KHONG_AP_DUNG
    assert result.vendor_profile is not None and result.vendor_profile.hinh_thuc == "độc lập"
