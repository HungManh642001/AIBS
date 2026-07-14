"""B1 — registry luật nghiệp vụ liên-tài-liệu: RuleSkill + RuleRegistry + dispatch_rules."""
import pytest

from experiment.evaluate.rules.registry import RuleRegistry, RuleSkill, default_registry, dispatch_rules
from experiment.evaluate.schema import (
    KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, PageRecord, VendorContext, Verdict,
)


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def _verdict(ket_qua):
    return Verdict(noi_dung_kiem_tra="Luật giả", hsdt_kiem_tra="don_du_thau", yeu_cau="",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung="", trang=[], do_tin=1.0,
                   ghi_chu="", nguon_doc=["don_du_thau"])


def _skill(id="luat_gia", can_vendor=False, handler=None, kich_hoat=None):
    async def _default_handler(by_type, ctx, crit, vision_fn):
        return _verdict(KET_QUA_KHONG)
    return RuleSkill(id=id, ten="Luật giả", ho_so_can=["don_du_thau"], can_vendor=can_vendor,
                     kich_hoat=kich_hoat or (lambda c: c.get("ten") == "Đơn dự thầu"),
                     handler=handler or _default_handler)


_CRIT = {"ten": "Đơn dự thầu", "nhom": "hop_le"}


def test_registry_matching_by_predicate():
    reg = RuleRegistry()
    reg.register(_skill())
    assert [s.id for s in reg.matching(_CRIT)] == ["luat_gia"]
    assert reg.matching({"ten": "Khác"}) == []
    assert default_registry().matching(_CRIT) == []      # B1: registry mặc định rỗng


async def test_dispatch_runs_matching_once_per_vendor():
    calls = []

    async def handler(by_type, ctx, crit, vision_fn):
        calls.append(crit["ten"])
        return _verdict(KET_QUA_KHONG)

    reg = RuleRegistry()
    reg.register(_skill(handler=handler))
    fired: set[str] = set()
    by_type = {"don_du_thau": [_p(1, "don_du_thau", "đơn")]}

    out1 = await dispatch_rules(reg, _CRIT, by_type, None, None, fired)
    assert [v.ket_qua for v in out1] == [KET_QUA_KHONG] and calls == ["Đơn dự thầu"]
    out2 = await dispatch_rules(reg, _CRIT, by_type, None, None, fired)   # đã bắn -> bỏ
    assert out2 == [] and calls == ["Đơn dự thầu"]


async def test_dispatch_can_vendor_without_ctx_returns_soi():
    called = []

    async def handler(by_type, ctx, crit, vision_fn):
        called.append(1)
        return _verdict(KET_QUA_KHONG)

    reg = RuleRegistry()
    reg.register(_skill(can_vendor=True, handler=handler))
    out = await dispatch_rules(reg, _CRIT, {}, None, None, set())
    assert [v.ket_qua for v in out] == [KET_QUA_SOI] and called == []     # KHÔNG gọi handler
    assert "nhà thầu" in out[0].ghi_chu

    # có ctx -> handler chạy bình thường
    ctx = VendorContext(ten="ABC")
    out2 = await dispatch_rules(reg, _CRIT, {}, ctx, None, set())
    assert [v.ket_qua for v in out2] == [KET_QUA_KHONG] and called == [1]


async def test_dispatch_handler_raise_becomes_loi():
    async def handler(by_type, ctx, crit, vision_fn):
        raise RuntimeError("nổ")

    reg = RuleRegistry()
    reg.register(_skill(handler=handler))
    out = await dispatch_rules(reg, _CRIT, {}, None, None, set())
    assert [v.ket_qua for v in out] == [KET_QUA_LOI]
    assert "nổ" in out[0].bang_chung
