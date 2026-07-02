import json
import fitz

from experiment.evaluate.run_evaluate import run
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
