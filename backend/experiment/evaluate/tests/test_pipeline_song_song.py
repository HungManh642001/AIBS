"""Tiêu chí và luật thường trực chạy SONG SONG trong một lượt chấm nhà thầu."""
from experiment.evaluate.rules.registry import (
    PHAM_VI_GOI, RuleRegistry, RuleSkill, dispatch_standing,
)
from experiment.evaluate.schema import PageRecord, Verdict
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _page(loai: str) -> PageRecord:
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text="nội dung")


def _skill(i: int) -> RuleSkill:
    async def handler(by_type, ctx, crit, vision_fn, *, nd=None, pkg=None):
        await vision_fn("sys", f"[RULE:{i}]")
        return Verdict(noi_dung_kiem_tra=f"luat{i}", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                       thong_tin_bo_sung="", ket_qua="đạt", bang_chung="", trang=[], do_tin=0.0,
                       ghi_chu="", nguon_doc=[])
    return RuleSkill(id=f"luat{i}", ten=f"luat{i}", ho_so_can=["don_du_thau"],
                     can_vendor=False, handler=handler, pham_vi=PHAM_VI_GOI)


async def test_luat_thuong_truc_chay_song_song():
    reg = RuleRegistry()
    for i in range(4):
        reg.register(_skill(i))
    vision = VisionDemDongThoi()
    out = await dispatch_standing(reg, {"don_du_thau": [_page("don_du_thau")]}, None, vision)
    assert vision.dinh > 1, "các luật thường trực vẫn chạy tuần tự"
    assert [v.noi_dung_kiem_tra for v in out] == [f"luat{i}" for i in range(4)]   # giữ thứ tự


async def test_cac_tieu_chi_cham_song_song(monkeypatch):
    import experiment.evaluate.pipeline as pl

    crits = [{"nhom": "hop_le", "ten": f"TC{i}", "hsdt_can_kiem_tra": ["don_du_thau"],
              "noi_dung_can_kiem_tra": [{"noi_dung_kiem_tra": f"nd{i}",
                                         "hsdt_kiem_tra": "don_du_thau", "yeu_cau": "có",
                                         "thong_tin_bo_sung": ""}]} for i in range(5)]
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})

    async def fake_ingest(files, vision_fn, dpi=200, cache=None):
        return [_page("don_du_thau")]

    monkeypatch.setattr(pl, "ingest_hsdt", fake_ingest)
    r = await pl.evaluate_hsdt(crits, [], vision_fn=vision, registry=RuleRegistry())
    assert vision.dinh > 1, "các tiêu chí vẫn chấm tuần tự"
    assert [c.ten for c in r.criteria] == [f"TC{i}" for i in range(5)]            # giữ thứ tự
