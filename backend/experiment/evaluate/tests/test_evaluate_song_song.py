"""Các nội dung trong một tiêu chí chấm SONG SONG — thứ tự verdict phải giữ nguyên."""
from experiment.evaluate.evaluate import evaluate_criterion
from experiment.evaluate.schema import KET_QUA_DAT, PageRecord
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi


def _page(loai: str, text: str = "nội dung") -> PageRecord:
    return PageRecord(file="f.pdf", trang=1, loai_ho_so=loai, text=text)


def _crit(n: int) -> dict:
    return {"nhom": "hop_le", "ten": "Tiêu chí", "hsdt_can_kiem_tra": ["don_du_thau"],
            "noi_dung_can_kiem_tra": [
                {"noi_dung_kiem_tra": f"nd{i}", "hsdt_kiem_tra": "don_du_thau",
                 "yeu_cau": "có", "thong_tin_bo_sung": ""} for i in range(n)]}


async def test_cac_noi_dung_cham_song_song():
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(_crit(5), [_page("don_du_thau")], vision)
    assert vision.so_call == 5
    assert vision.dinh > 1, "các nội dung vẫn chấm tuần tự"
    assert ce.ket_qua == KET_QUA_DAT


async def test_thu_tu_verdict_giu_nguyen():
    """gather giữ thứ tự — verdict phải khớp đúng thứ tự nội dung trong tiêu chí."""
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(_crit(6), [_page("don_du_thau")], vision)
    assert [v.noi_dung_kiem_tra for v in ce.verdicts] == [f"nd{i}" for i in range(6)]


async def test_gate_na_van_chay_truoc_va_khong_ton_call():
    """Nội dung bị gate 'không áp dụng' phải ra verdict N/A mà KHÔNG gọi vision — gate là nhánh
    đồng bộ, không được kéo vào gather."""
    from experiment.evaluate.schema import KET_QUA_KHONG_AP_DUNG, VendorProfile

    crit = _crit(2)
    crit["noi_dung_can_kiem_tra"][0]["ap_dung"] = "lien_danh"
    vision = VisionDemDongThoi({"ket_qua": "đạt", "bang_chung": "x"})
    ce = await evaluate_criterion(
        crit, [_page("don_du_thau")], vision,
        profile=VendorProfile(hinh_thuc="độc lập", nguon="khai báo", do_tin=1.0))
    assert ce.verdicts[0].ket_qua == KET_QUA_KHONG_AP_DUNG
    assert vision.so_call == 1                    # chỉ nội dung còn lại tốn call
