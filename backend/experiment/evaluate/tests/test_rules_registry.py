"""Registry luật liên-tài-liệu: khớp TẤT ĐỊNH theo ho_so_can ⊆ hsdt_can_kiem_tra (không predicate tay)."""
from experiment.evaluate.rules.registry import (
    PHAM_VI_GOI, PHAM_VI_TIEU_CHI, RuleRegistry, RuleSkill, default_registry, dispatch_standing,
    run_skill,
)
from experiment.evaluate.schema import (
    KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, PageRecord, VendorContext, Verdict,
)


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def _verdict(ket_qua):
    return Verdict(noi_dung_kiem_tra="Luật giả", hsdt_kiem_tra="bang_gia", yeu_cau="",
                   thong_tin_bo_sung="", ket_qua=ket_qua, bang_chung="", trang=[], do_tin=1.0,
                   ghi_chu="", nguon_doc=["bang_gia", "webform"])


def _skill(id="luat_gia", can_vendor=False, handler=None, ho_so_can=None,
           pham_vi=PHAM_VI_TIEU_CHI):
    async def _default_handler(by_type, ctx, crit, vision_fn, *, nd=None):
        return _verdict(KET_QUA_KHONG)
    return RuleSkill(id=id, ten="Luật giả", ho_so_can=ho_so_can or ["bang_gia", "webform"],
                     can_vendor=can_vendor, handler=handler or _default_handler, pham_vi=pham_vi)


def _crit(*ho_so):
    return {"ten": "Tiêu chí", "nhom": "hop_le", "hsdt_can_kiem_tra": list(ho_so)}


def test_matching_requires_criterion_to_declare_full_doc_set():
    """Tiêu chí phải khai ĐỦ bộ hồ sơ luật cần — đây là cái chặn luật bắn nhầm tiêu chí."""
    reg = RuleRegistry()
    reg.register(_skill())
    assert [s.id for s in reg.matching(_crit("bang_gia", "webform"))] == ["luat_gia"]
    assert reg.matching(_crit("bang_gia")) == []            # 'Bảng giá đúng mẫu' -> KHÔNG khớp
    assert reg.matching(_crit()) == []
    assert reg.matching({"ten": "Không khai"}) == []


def test_matching_normalizes_and_allows_superset():
    reg = RuleRegistry()
    reg.register(_skill())
    assert [s.id for s in reg.matching(_crit("Bang_Gia", "WebForm"))] == ["luat_gia"]
    # khai thừa vẫn khớp (⊆, không phải ==)
    assert [s.id for s in reg.matching(_crit("bang_gia", "webform", "don_du_thau"))] == ["luat_gia"]


def test_matching_excludes_standing_skills():
    """Luật phạm vi gói KHÔNG bao giờ gắn vào tiêu chí."""
    reg = RuleRegistry()
    reg.register(_skill(id="standing", pham_vi=PHAM_VI_GOI, ho_so_can=["bang_gia"]))
    assert reg.matching(_crit("bang_gia", "webform")) == []
    assert [s.id for s in reg.standing()] == ["standing"]


def test_default_registry_scopes():
    reg = default_registry()
    assert [s.id for s in reg.standing()] == ["chu_ky_khop_dkkd"]       # chữ ký = standing
    assert [s.id for s in reg.matching(_crit("bang_gia", "webform"))] == ["bang_gia_khop_webform"]
    assert reg.matching(_crit("don_du_thau")) == []                     # chữ ký không gắn tiêu chí
    assert reg.matching(_crit("bang_gia")) == []


async def test_run_skill_can_vendor_without_ctx_returns_soi():
    called = []

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None):
        called.append(1)
        return _verdict(KET_QUA_KHONG)

    got = await run_skill(_skill(can_vendor=True, handler=handler), {}, None, _crit(), None)
    assert got.ket_qua == KET_QUA_SOI and called == []      # KHÔNG gọi handler
    assert "nhà thầu" in got.ghi_chu

    got2 = await run_skill(_skill(can_vendor=True, handler=handler), {}, VendorContext(ten="ABC"),
                           _crit(), None)
    assert got2.ket_qua == KET_QUA_KHONG and called == [1]


async def test_run_skill_handler_raise_becomes_loi():
    async def handler(by_type, ctx, crit, vision_fn, *, nd=None):
        raise RuntimeError("nổ")

    got = await run_skill(_skill(handler=handler), {}, None, _crit(), None)
    assert got.ket_qua == KET_QUA_LOI and "nổ" in got.bang_chung


async def test_run_skill_passes_nd_to_handler():
    seen = {}

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None):
        seen["nd"] = nd
        return _verdict(KET_QUA_KHONG)

    nd = {"noi_dung_kiem_tra": "Giá khớp webform", "hsdt_kiem_tra": "bang_gia"}
    await run_skill(_skill(handler=handler), {}, None, _crit(), None, nd=nd)
    assert seen["nd"] == nd


async def test_dispatch_standing_runs_each_once():
    calls = []

    async def handler(by_type, ctx, crit, vision_fn, *, nd=None):
        calls.append(1)
        return _verdict(KET_QUA_KHONG)

    reg = RuleRegistry()
    reg.register(_skill(id="standing", pham_vi=PHAM_VI_GOI, handler=handler))
    reg.register(_skill(id="theo_tieu_chi", handler=handler))     # KHÔNG được chạy ở đây
    out = await dispatch_standing(reg, {"don_du_thau": [_p(1, "don_du_thau", "đơn")]}, None, None)
    assert [v.ket_qua for v in out] == [KET_QUA_KHONG] and calls == [1]
