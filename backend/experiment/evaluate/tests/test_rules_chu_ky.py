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
    assert SKILL.ho_so_can == ["don_du_thau", "dang_ky_kinh_doanh"]
    assert SKILL.pham_vi == PHAM_VI_GOI

    reg = RuleRegistry()
    reg.register(SKILL)
    assert [s.id for s in reg.standing()] == ["chu_ky_khop_dkkd"]
    # dù tiêu chí khai đủ cả 2 hồ sơ, luật standing vẫn KHÔNG gắn vào tiêu chí
    assert reg.matching({"ten": "Đơn dự thầu",
                         "hsdt_can_kiem_tra": ["don_du_thau", "dang_ky_kinh_doanh"]}) == []


_BY_TYPE = {
    "don_du_thau": [_p(1, "don_du_thau", "Đơn dự thầu... Người ký: Nguyễn Văn A (Giám đốc)")],
    "dang_ky_kinh_doanh": [_p(1, "dang_ky_kinh_doanh", "ĐKKD... Người đại diện theo pháp luật: Nguyễn Văn A")],
}


async def test_handler_dat_khong_dat_soi():
    ok = ScriptedVision({"[RULE:chu_ky_khop_dkkd]": {
        "ket_qua": "đạt", "nguoi_ky": "Nguyễn Văn A", "dai_dien_phap_luat": "Nguyễn Văn A",
        "bang_chung": "đơn ký A; ĐKKD đại diện A", "trang": [1], "do_tin": 0.9}})
    v = await SKILL.handler(_BY_TYPE, None, {}, ok)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["don_du_thau", "dang_ky_kinh_doanh"]
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


_LECH = {"[RULE:chu_ky_khop_dkkd]": {
    "ket_qua": "không đạt", "nguoi_ky": "Trần Văn B", "dai_dien_phap_luat": "Nguyễn Văn A",
    "bang_chung": "ký B ≠ đại diện A", "trang": [1]}}

_BY_TYPE_GUQ = {**_BY_TYPE, "giay_uy_quyen": [
    _p(1, "giay_uy_quyen", "GIẤY ỦY QUYỀN: Nguyễn Văn A ủy quyền cho Trần Văn B ký đơn dự thầu")]}


async def test_handler_khong_khop_no_guq_khong_dat():
    """Người ký ≠ đại diện PL và HSDT KHÔNG có giấy ủy quyền -> 'không đạt', KHÔNG gọi LLM lần 2."""
    vision = ScriptedVision(dict(_LECH))
    v = await SKILL.handler(_BY_TYPE, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG
    assert "ủy quyền" in v.ghi_chu                          # nêu rõ lý do: không có GUQ
    assert len(vision.calls) == 1


async def test_handler_khong_khop_guq_hop_le_dat():
    """Ký thay + GUQ hợp lệ (đúng người, đúng phạm vi) -> 'đạt'; call 2 phải thấy tên 2 phía + GUQ."""
    vision = ScriptedVision({**_LECH, "[RULE:chu_ky_uy_quyen]": {
        "ket_qua": "đạt", "nguoi_uy_quyen": "Nguyễn Văn A", "nguoi_duoc_uy_quyen": "Trần Văn B",
        "bang_chung": "GUQ: A ủy quyền B ký đơn dự thầu", "trang": [1], "do_tin": 0.9}})
    v = await SKILL.handler(_BY_TYPE_GUQ, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT
    assert "giay_uy_quyen" in v.nguon_doc                   # audit: đã đối chiếu GUQ
    assert "ủy quyền" in v.bang_chung
    assert len(vision.calls) == 2
    hay2 = vision.calls[-1][0]
    assert "Trần Văn B" in hay2 and "Nguyễn Văn A" in hay2 and "GIẤY ỦY QUYỀN" in hay2


async def test_handler_khong_khop_guq_khong_cho_ky_thay():
    """GUQ có nhưng sai người/không cho ký thay đơn dự thầu -> 'không đạt'."""
    vision = ScriptedVision({**_LECH, "[RULE:chu_ky_uy_quyen]": {
        "ket_qua": "không đạt", "nguoi_uy_quyen": "Nguyễn Văn A", "nguoi_duoc_uy_quyen": "Lê C",
        "bang_chung": "GUQ ủy quyền cho Lê C, không phải người ký Trần Văn B", "trang": [1]}})
    v = await SKILL.handler(_BY_TYPE_GUQ, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG and "giay_uy_quyen" in v.nguon_doc


async def test_handler_guq_call_error_becomes_loi():
    """Call thẩm định GUQ lỗi -> verdict 'lỗi' (no-silent-mock), không rơi về kết luận bịa."""
    vision = ScriptedVision(dict(_LECH))                    # KHÔNG có kịch bản call 2
    v = await SKILL.handler(_BY_TYPE_GUQ, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI


async def test_handler_bang_chung_luon_neu_ai_uy_quyen_cho_ai():
    """Chuyên gia phải đọc được AI ỦY QUYỀN CHO AI ngay trên bằng chứng, kể cả khi LLM không nêu."""
    vision = ScriptedVision({**_LECH, "[RULE:chu_ky_uy_quyen]": {
        "ket_qua": "đạt", "nguoi_uy_quyen": "Nguyễn Văn A", "nguoi_duoc_uy_quyen": "Trần Văn B",
        "bang_chung": "trích GUQ: phạm vi gồm ký đơn dự thầu", "trang": [1]}})
    v = await SKILL.handler(_BY_TYPE_GUQ, None, {}, vision)
    assert "Nguyễn Văn A ủy quyền cho Trần Văn B" in v.bang_chung
    assert "phạm vi gồm ký đơn dự thầu" in v.bang_chung      # KHÔNG nuốt trích dẫn của LLM


# HSDT thiếu ĐKKD nhưng có GUQ — thực tế hay gặp, không được bỏ qua kiểm tra chữ ký.
_BY_TYPE_KHONG_DKKD = {
    "don_du_thau": _BY_TYPE["don_du_thau"],
    "giay_uy_quyen": _BY_TYPE_GUQ["giay_uy_quyen"],
}


async def test_handler_khong_co_dkkd_guq_hop_le_dat():
    """Không có ĐKKD + có GUQ -> thẩm định GUQ độc lập (đúng người ký + đúng phạm vi) -> 'đạt'."""
    vision = ScriptedVision({"[RULE:chu_ky_uy_quyen_khong_dkkd]": {
        "ket_qua": "đạt", "nguoi_uy_quyen": "Nguyễn Văn A", "nguoi_duoc_uy_quyen": "Trần Văn B",
        "bang_chung": "GUQ: phạm vi gồm ký đơn dự thầu", "trang": [1], "do_tin": 0.85}})
    v = await SKILL.handler(_BY_TYPE_KHONG_DKKD, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT
    assert v.nguon_doc == ["don_du_thau", "giay_uy_quyen"]   # audit: KHÔNG có ĐKKD trong nguồn
    assert "Nguyễn Văn A ủy quyền cho Trần Văn B" in v.bang_chung
    assert "ĐKKD" in v.ghi_chu                              # nêu rõ chưa đối chiếu được ĐKKD
    assert len(vision.calls) == 1                           # KHÔNG gọi bước đối chiếu ĐKKD
    hay = vision.calls[-1][0]
    assert "Người ký: Nguyễn Văn A" in hay                  # đơn dự thầu vào prompt (chưa bóc tên)
    assert "GIẤY ỦY QUYỀN" in hay


async def test_handler_khong_co_dkkd_guq_sai_nguoi_khong_dat():
    vision = ScriptedVision({"[RULE:chu_ky_uy_quyen_khong_dkkd]": {
        "ket_qua": "không đạt", "nguoi_uy_quyen": "Nguyễn Văn A", "nguoi_duoc_uy_quyen": "Lê C",
        "bang_chung": "GUQ ủy quyền cho Lê C, không phải người ký đơn", "trang": [1]}})
    v = await SKILL.handler(_BY_TYPE_KHONG_DKKD, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG
    assert "Nguyễn Văn A ủy quyền cho Lê C" in v.bang_chung


async def test_handler_khong_co_dkkd_guq_call_error_becomes_loi():
    vision = ScriptedVision({})                             # không kịch bản -> proxy lỗi
    v = await SKILL.handler(_BY_TYPE_KHONG_DKKD, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI


async def test_handler_missing_doc_thieu_no_llm():
    vision = ScriptedVision({})
    v = await SKILL.handler({"don_du_thau": _BY_TYPE["don_du_thau"]}, None, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "dang_ky_kinh_doanh" in v.bang_chung
    assert vision.calls == []                               # thiếu hồ sơ -> KHÔNG gọi LLM

    v2 = await SKILL.handler({}, None, {}, vision)
    assert v2.ket_qua == KET_QUA_THIEU and "don_du_thau" in v2.bang_chung


async def test_handler_missing_don_du_thau_thieu_du_co_guq():
    """Thiếu ĐƠN DỰ THẦU thì GUQ cũng vô nghĩa (không có chữ ký để đối chiếu) -> 'thiếu hồ sơ'."""
    vision = ScriptedVision({})
    v = await SKILL.handler({"giay_uy_quyen": _BY_TYPE_GUQ["giay_uy_quyen"]}, None, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "don_du_thau" in v.bang_chung
    assert vision.calls == []


async def test_handler_ai_error_becomes_loi_via_dispatch():
    """AI lỗi -> vision trả error -> verdict 'lỗi' (qua dispatch standing, không nuốt)."""
    from experiment.evaluate.rules.registry import RuleRegistry, dispatch_standing

    reg = RuleRegistry()
    reg.register(SKILL)
    out = await dispatch_standing(reg, _BY_TYPE, None, ScriptedVision({}))
    assert [v.ket_qua for v in out] == [KET_QUA_LOI]        # kịch bản không khớp = proxy lỗi
