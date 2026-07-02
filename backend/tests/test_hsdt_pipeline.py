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
