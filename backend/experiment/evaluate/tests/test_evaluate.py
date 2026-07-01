from experiment.evaluate.evaluate import eval_noi_dung, evaluate_criterion
from experiment.evaluate.vision import ScriptedVision
from experiment.evaluate.schema import PageRecord, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_THIEU


def _page(loai, text, image=b"\x89PNG", co_chu_ky=False):
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text, co_chu_ky=co_chu_ky, image=image)


def _nd(noi_dung, hsdt, kieu="đối chiếu"):
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": hsdt, "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ", "kieu_check": kieu}


async def test_eval_noi_dung_missing_doc_is_thieu_ho_so():
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("don_du_thau", "đơn")], ScriptedVision({}))
    assert v.ket_qua == KET_QUA_THIEU     # không có trang bảo đảm dự thầu


async def test_eval_noi_dung_pass_from_text():
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "đạt", "bang_chung": "6.100.000", "trang": [1], "do_tin": 0.9}})
    v = await eval_noi_dung(_nd("Giá trị bảo lãnh", "bao_dam_du_thau"),
                            [_page("bao_dam_du_thau", "bảo lãnh 6.100.000 VNĐ")], vision)
    assert v.ket_qua == KET_QUA_DAT and v.trang == [1]
    assert v.thong_tin_bo_sung == "6.100.000 VNĐ"   # chuẩn HSMT lưu vào verdict để audit
    assert vision.calls[-1][1] == 0                 # check đối chiếu -> KHÔNG đính ảnh


async def test_eval_noi_dung_visual_check_attaches_image():
    vision = ScriptedVision({"[EV:Chữ ký đóng dấu]":
                             {"ket_qua": "đạt", "bang_chung": "có chữ ký", "trang": [1], "do_tin": 0.8}})
    await eval_noi_dung(_nd("Chữ ký đóng dấu", "bao_dam_du_thau", kieu="chữ ký & đóng dấu"),
                        [_page("bao_dam_du_thau", "thư bảo lãnh", co_chu_ky=True)], vision)
    assert vision.calls[-1][1] == 1                 # check thị giác -> đính 1 ảnh


async def test_criterion_rollup_blocking_fail_marks_loai():
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "không đạt", "bang_chung": "3 triệu < 6.1tr", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("bao_dam_du_thau", "bảo lãnh 3.000.000")], vision)
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True
