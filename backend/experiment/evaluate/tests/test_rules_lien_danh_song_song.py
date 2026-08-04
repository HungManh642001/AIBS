"""Các chunk bảng giá đọc SONG SONG (bảng thật 15 trang ≈ 68.000 ký tự -> nhiều chunk)."""
from experiment.evaluate.rules.lien_danh_phan_cong import SKILL
from experiment.evaluate.schema import KET_QUA_LOI, PageRecord
from experiment.evaluate.tests.dong_thoi import VisionDemDongThoi
from services.ai_client import AiOutcome


def _p(trang: int, loai: str, text: str) -> PageRecord:
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


_TTLD = {"thanh_vien": [{"ten": "Công ty A", "mo_ta_cong_viec": "hạng mục 1",
                         "neu_ro_hang_muc": True, "ty_le_khai": 100.0}],
         "trang": [1], "ghi_chu": ""}


def _by_type(n_chunk: int) -> dict[str, list[PageRecord]]:
    """Mỗi trang bảng giá dài hơn ngân sách chunk -> mỗi trang thành một chunk riêng."""
    dai = "x" * 7000
    return {"thoa_thuan_lien_danh": [_p(1, "thoa_thuan_lien_danh", "bảng phân công")],
            "bang_gia": [_p(i, "bang_gia", dai) for i in range(1, n_chunk + 1)]}


class _Vision(VisionDemDongThoi):
    """Trả TTLD cho call giai đoạn 1, dữ liệu chunk cho các call sau."""

    async def __call__(self, system, prompt, images=(), validate=None, **kw):
        if "[RULE:lien_danh_ttld]" in prompt:
            self._data = dict(_TTLD)
        else:
            self._data = {"hang_muc": [{"stt": "1", "ten": "hm", "thanh_tien": 100.0,
                                        "thanh_vien": "Công ty A"}],
                          "dong_tong": [{"nhan": "TỔNG CỘNG", "gia_tri": 100.0}]}
        return await super().__call__(system, prompt, images, validate, **kw)


async def test_cac_chunk_doc_song_song():
    vision = _Vision()
    await SKILL.handler(_by_type(5), None, {}, vision)
    assert vision.dinh > 1, "các chunk bảng giá vẫn đọc tuần tự"


async def test_chunk_loi_van_bao_dung_chi_so_dau_tien():
    """Verdict không đổi: báo lỗi kèm chỉ số chunk lỗi ĐẦU TIÊN theo thứ tự, không phải chunk
    nào lỗi trước về đích."""
    class _Hong(_Vision):
        async def __call__(self, system, prompt, images=(), validate=None, **kw):
            if "[RULE:lien_danh_bang_gia]" in prompt and "x" * 100 in prompt:
                self.so_call += 1
                return AiOutcome("error", None, "fake", error="proxy hỏng")
            return await super().__call__(system, prompt, images, validate, **kw)

    v = await SKILL.handler(_by_type(3), None, {}, _Hong())
    assert v.ket_qua == KET_QUA_LOI
    assert "phần 1/3" in v.bang_chung
