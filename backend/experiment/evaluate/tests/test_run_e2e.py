import json
import fitz

from experiment.evaluate.run_evaluate import _parse_vendor, run
from experiment.evaluate.schema import VendorContext
from experiment.evaluate.vision import ScriptedVision


def _pdf(text):
    d = fitz.open(); p = d.new_page(); p.insert_text((72, 72), text)
    return d.tobytes()


async def test_run_e2e_legality(tmp_path):
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [{
        "nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
        "noi_dung_can_kiem_tra": [{"noi_dung_kiem_tra": "Giá trị bảo lãnh",
            "hsdt_kiem_tra": "bao_dam_du_thau", "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ"}]}]},
        {"group": "tai_chinh", "criteria": [{"nhom": "tai_chinh", "ten": "Giá", "noi_dung_can_kiem_tra": []}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")

    vision = ScriptedVision({
        "[IN]": {"text": "Thư bảo lãnh 6.100.000 VNĐ", "co_dau": True},   # vision chỉ bóc text
        "[EV:Giá trị bảo lãnh]": {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9},
    })
    out = tmp_path / "out"
    # file HSDT kèm mã catalog đã biết: (tên, loai_ho_so, data)
    metrics = await run(str(dp), [("bao_lanh.pdf", "bao_dam_du_thau", _pdf("bảo lãnh"))], str(out),
                        doc="HSDT-NhaThauA", vision_fn=vision)

    assert metrics["n_tieu_chi"] == 1 and metrics["n_dat"] == 1   # CHỈ nhóm hop_le
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert data["doc"] == "HSDT-NhaThauA"
    assert data["criteria"][0]["ket_qua"] == "đạt"
    assert "image" not in str(data)                              # ảnh không lọt JSON
    assert (out / "evaluation.md").exists()


def test_parse_vendor():
    assert _parse_vendor("Công ty ABC|0312345678|abc jsc;lien danh abc") == VendorContext(
        ten="Công ty ABC", ma_so_thue="0312345678", aliases=["abc jsc", "lien danh abc"])
    assert _parse_vendor("Công ty ABC") == VendorContext(ten="Công ty ABC")
    assert _parse_vendor("") is None


def _decomp_don(tmp_path):
    decomp = {"doc": "E-HSMT", "groups": [{"group": "hop_le", "muc": "Mục 1", "criteria": [{
        "nhom": "hop_le", "ten": "Đơn dự thầu", "tien_quyet": True,
        "noi_dung_can_kiem_tra": [
            {"noi_dung_kiem_tra": "Có đơn dự thầu", "hsdt_kiem_tra": "don_du_thau",
             "yeu_cau": "phải có", "thong_tin_bo_sung": ""},
            {"noi_dung_kiem_tra": "Bảng giá đúng mẫu", "hsdt_kiem_tra": "bang_gia",
             "yeu_cau": "đúng mẫu 05C.1", "thong_tin_bo_sung": ""}]}]}]}
    dp = tmp_path / "decomposition.json"
    dp.write_text(json.dumps(decomp, ensure_ascii=False), encoding="utf-8")
    return str(dp)


_FILES = [("don.pdf", "don_du_thau", None), ("dkkd.pdf", "tu_cach_phap_ly", None),
          ("bg.pdf", "bang_gia", None), ("webform.pdf", "webform", None)]


def _files():
    return [(n, c, _pdf(n)) for n, c, _ in _FILES]


def _vision_full():
    return ScriptedVision({
        "[IN]": {"text": "Công ty TNHH ABC | 1.200.000.000 | ký Nguyễn Văn A"},
        "[EV:Có đơn dự thầu]": {"ket_qua": "đạt", "bang_chung": "có đơn", "trang": [1]},
        "[EV:Bảng giá đúng mẫu]": {"ket_qua": "đạt", "bang_chung": "đúng mẫu", "trang": [1]},
        "[RULE:chu_ky_khop_dkkd]": {"ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A",
                                    "dai_dien_phap_luat": "Nguyễn Văn A", "bang_chung": "khớp", "trang": [1]},
        "[RULE:bang_gia_khop_webform]": {"ket_qua": "đạt", "bang_chung": "1.2 tỷ khớp", "trang": [1]},
    })


async def test_run_e2e_rules_with_vendor(tmp_path):
    """--vendor + webform: verdict 2 luật xuất hiện trong evaluation.json kèm nguon_doc."""
    out = tmp_path / "out"
    metrics = await run(_decomp_don(tmp_path), _files(), str(out), doc="HSDT-A",
                        vision_fn=_vision_full(),
                        vendor=VendorContext(ten="Công ty TNHH ABC"))
    assert metrics["n_dat"] == 1
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    verdicts = data["criteria"][0]["verdicts"]
    rule_v = {v["noi_dung_kiem_tra"]: v for v in verdicts if v["nguon_doc"]}
    assert set(rule_v) == {"Người ký đơn dự thầu khớp đại diện pháp luật (ĐKKD)",
                           "Bảng giá khớp giá trên webform"}
    assert rule_v["Bảng giá khớp giá trên webform"]["nguon_doc"] == ["bang_gia", "webform"]


async def test_run_e2e_rules_without_vendor_soi(tmp_path):
    """Không --vendor: luật can_vendor trả 'cần làm rõ' (không crash, không gọi handler)."""
    out = tmp_path / "out"
    await run(_decomp_don(tmp_path), _files(), str(out), doc="HSDT-A", vision_fn=_vision_full())
    data = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    v = next(v for v in data["criteria"][0]["verdicts"]
             if v["noi_dung_kiem_tra"] == "Bảng giá khớp giá trên webform")
    assert v["ket_qua"] == "cần làm rõ" and "nhà thầu" in v["ghi_chu"]
