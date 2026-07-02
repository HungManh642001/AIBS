from experiment.evaluate.evaluate import eval_noi_dung, evaluate_criterion
from experiment.evaluate.vision import ScriptedVision
from experiment.evaluate.schema import PageRecord, KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_THIEU


def _page(loai, text, image=b"\x89PNG", co_chu_ky=False):
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text, co_chu_ky=co_chu_ky, image=image)


def _nd(noi_dung, hsdt):
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": hsdt, "yeu_cau": "theo HSMT",
            "thong_tin_bo_sung": "6.100.000 VNĐ"}


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
    assert vision.calls[-1][1] == 0                 # eval THUẦN TEXT -> KHÔNG bao giờ đính ảnh


async def test_eval_signature_check_from_ingest_text():
    # Chữ ký/dấu đã được ingest mô tả trong text + cờ -> eval kết luận trên text, KHÔNG cần ảnh.
    vision = ScriptedVision({"[EV:Chữ ký & đóng dấu]":
                             {"ket_qua": "đạt", "bang_chung": "có chữ ký và con dấu đỏ", "trang": [1]}})
    v = await eval_noi_dung(_nd("Chữ ký & đóng dấu", "bao_dam_du_thau"),
                            [_page("bao_dam_du_thau", "Thư bảo lãnh (có chữ ký; có đóng dấu)", co_chu_ky=True)],
                            vision)
    assert v.ket_qua == KET_QUA_DAT
    assert vision.calls[-1][1] == 0                 # không đính ảnh


async def test_criterion_rollup_blocking_fail_marks_loai():
    crit = {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "tien_quyet": True,
            "noi_dung_can_kiem_tra": [_nd("Giá trị bảo lãnh", "bao_dam_du_thau")]}
    vision = ScriptedVision({"[EV:Giá trị bảo lãnh]":
                             {"ket_qua": "không đạt", "bang_chung": "3 triệu < 6.1tr", "trang": [1]}})
    ce = await evaluate_criterion(crit, [_page("bao_dam_du_thau", "bảo lãnh 3.000.000")], vision)
    assert ce.ket_qua == KET_QUA_KHONG and ce.loai is True
