"""B2 — luật chu_ky_khop_dkkd: người ký đơn dự thầu ↔ đại diện pháp luật trong ĐKKD."""
from experiment.evaluate.rules.chu_ky_khop_dkkd import (
    SKILL, SYS_RULE_CHU_KY, chu_ky_prompt, validate_chu_ky,
)
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_SOI, KET_QUA_THIEU, PageRecord,
)
from experiment.evaluate.vision import ScriptedVision


def _p(trang, loai, text):
    return PageRecord(file="f.pdf", trang=trang, loai_ho_so=loai, text=text)


def test_chu_ky_prompt_marker_and_caps():
    p = chu_ky_prompt("ĐƠN: ký bởi Nguyễn Văn A" + "x" * 5000, "ĐKKD: đại diện Nguyễn Văn A")
    assert "[RULE:chu_ky_khop_dkkd]" in p
    assert "ĐƠN: ký bởi Nguyễn Văn A" in p and "ĐKKD: đại diện Nguyễn Văn A" in p
    assert len(p) < 8000                                    # cap per-doc (~3000/tài liệu)
    assert "KHÔNG bịa" in SYS_RULE_CHU_KY


def test_validate_chu_ky_tolerant():
    out = validate_chu_ky({"ket_qua": "đạt", "nguoi_ky": "A", "dai_dien_phap_luat": "A"})
    assert out["ket_qua"] == "đạt" and out["trang"] == [] and out["do_tin"] == 0.0


def test_skill_is_standing_not_attached_to_criterion():
    """Standing check: luôn chạy 1 lần/nhà thầu, KHÔNG gắn vào tiêu chí nào (chống quy kết sai)."""
    from experiment.evaluate.rules.registry import PHAM_VI_GOI, RuleRegistry

    assert SKILL.id == "chu_ky_khop_dkkd" and SKILL.can_vendor is False
    assert SKILL.ho_so_can == ["don_du_thau", "tu_cach_phap_ly"]
    assert SKILL.pham_vi == PHAM_VI_GOI

    reg = RuleRegistry()
    reg.register(SKILL)
    assert [s.id for s in reg.standing()] == ["chu_ky_khop_dkkd"]
    # dù tiêu chí khai đủ cả 2 hồ sơ, luật standing vẫn KHÔNG gắn vào tiêu chí
    assert reg.matching({"ten": "Đơn dự thầu",
                         "hsdt_can_kiem_tra": ["don_du_thau", "tu_cach_phap_ly"]}) == []


_BY_TYPE = {
    "don_du_thau": [_p(1, "don_du_thau", "Đơn dự thầu... Người ký: Nguyễn Văn A (Giám đốc)")],
    "tu_cach_phap_ly": [_p(1, "tu_cach_phap_ly", "ĐKKD... Người đại diện theo pháp luật: Nguyễn Văn A")],
}


async def test_handler_dat_khong_dat_soi():
    ok = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A", "dai_dien_phap_luat": "Nguyễn Văn A",
        "bang_chung": "đơn ký A; ĐKKD đại diện A", "trang": [1], "do_tin": 0.9}})
    v = await SKILL.handler(_BY_TYPE, None, {}, ok)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["don_du_thau", "tu_cach_phap_ly"]
    assert v.bang_chung == "đơn ký A; ĐKKD đại diện A"
    assert ok.calls[-1][1] == 0                             # text-only, không đính ảnh

    # bang_chung rỗng -> dựng từ nguoi_ky/dai_dien_phap_luat (vẫn có căn cứ đọc được)
    thieu_bc = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A", "dai_dien_phap_luat": "Nguyễn Văn A"}})
    vb = await SKILL.handler(_BY_TYPE, None, {}, thieu_bc)
    assert "Nguyễn Văn A" in vb.bang_chung

    lech = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "không đạt", "nguoi_ky": "Trần B", "dai_dien_phap_luat": "Nguyễn Văn A",
        "bang_chung": "ký B ≠ đại diện A", "trang": [1]}})
    v2 = await SKILL.handler(_BY_TYPE, None, {}, lech)
    assert v2.ket_qua == KET_QUA_KHONG

    mo_ho = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {"ket_qua": "cần làm rõ", "ghi_chu": "không thấy tên"}})
    v3 = await SKILL.handler(_BY_TYPE, None, {}, mo_ho)
    assert v3.ket_qua == KET_QUA_SOI


async def test_handler_missing_doc_thieu_no_llm():
    vision = ScriptedVision({})
    v = await SKILL.handler({"don_du_thau": _BY_TYPE["don_du_thau"]}, None, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "tu_cach_phap_ly" in v.bang_chung
    assert vision.calls == []                               # thiếu hồ sơ -> KHÔNG gọi LLM

    v2 = await SKILL.handler({}, None, {}, vision)
    assert v2.ket_qua == KET_QUA_THIEU and "don_du_thau" in v2.bang_chung


async def test_handler_ai_error_becomes_loi_via_dispatch():
    """AI lỗi -> vision trả error -> verdict 'lỗi' (qua dispatch standing, không nuốt)."""
    from experiment.evaluate.rules.registry import RuleRegistry, dispatch_standing

    reg = RuleRegistry()
    reg.register(SKILL)
    out = await dispatch_standing(reg, _BY_TYPE, None, ScriptedVision({}))
    assert [v.ket_qua for v in out] == [KET_QUA_LOI]        # kịch bản không khớp = proxy lỗi
