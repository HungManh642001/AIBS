"""Luật chu_ky_bao_dam_uy_quyen: người ký thư bảo lãnh không phải người đứng đầu -> cần GUQ hợp lệ."""
from experiment.evaluate.rules.bao_dam_uy_quyen import (
    SKILL, SYS_RULE_BAO_DAM, bao_dam_prompt, validate_bao_dam,
)
from experiment.evaluate.rules.registry import PHAM_VI_GOI
from experiment.evaluate.schema import (
    KET_QUA_DAT, KET_QUA_KHONG, KET_QUA_LOI, KET_QUA_THIEU, PageRecord,
)
from experiment.evaluate.vision import ScriptedVision


def _p(trang, text):
    return PageRecord(file="bl.pdf", trang=trang, loai_ho_so="bao_dam_du_thau", text=text)


def test_skill_is_standing_on_bao_dam():
    assert SKILL.id == "chu_ky_bao_dam_uy_quyen"
    assert SKILL.pham_vi == PHAM_VI_GOI
    assert SKILL.ho_so_can == ["bao_dam_du_thau"]
    assert SKILL.can_vendor is False and SKILL.can_pkg is False


def test_prompt_marker_cap_and_sys_mentions_uy_quyen():
    p = bao_dam_prompt("THƯ BẢO LÃNH..." + "x" * 9000)
    assert "[RULE:chu_ky_bao_dam_uy_quyen]" in p and "THƯ BẢO LÃNH" in p
    assert len(p) < 8000                                    # cap text tài liệu
    assert "ủy quyền" in SYS_RULE_BAO_DAM and "KHÔNG bịa" in SYS_RULE_BAO_DAM


def test_validate_tolerant():
    out = validate_bao_dam({"ket_qua": "đạt", "nguoi_ky": "A", "chuc_danh": "Giám đốc"})
    assert out["ket_qua"] == "đạt" and out["trang"] == [] and out["co_uy_quyen"] is False


async def test_handler_missing_doc_thieu_no_llm():
    vision = ScriptedVision({})
    v = await SKILL.handler({}, None, {}, vision)
    assert v.ket_qua == KET_QUA_THIEU and "bao_dam_du_thau" in v.bang_chung
    assert vision.calls == []


async def test_handler_giam_doc_ky_dat():
    vision = ScriptedVision({"[RULE:chu_ky_bao_dam_uy_quyen]": {
        "ket_qua": "đạt", "nguoi_ky": "Lê Thị C", "chuc_danh": "Tổng giám đốc",
        "bang_chung": "TGĐ ký trực tiếp", "trang": [1], "do_tin": 0.9}})
    by_type = {"bao_dam_du_thau": [_p(1, "THƯ BẢO LÃNH... Tổng giám đốc Lê Thị C (có chữ ký)")]}
    v = await SKILL.handler(by_type, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT and v.nguon_doc == ["bao_dam_du_thau"]
    assert "THƯ BẢO LÃNH" in vision.calls[-1][0]            # text bảo lãnh vào prompt


async def test_handler_ky_thay_khong_guq_khong_dat():
    vision = ScriptedVision({"[RULE:chu_ky_bao_dam_uy_quyen]": {
        "ket_qua": "không đạt", "nguoi_ky": "Phạm D", "chuc_danh": "Phó giám đốc chi nhánh",
        "co_uy_quyen": False, "bang_chung": "PGĐ ký, không thấy giấy ủy quyền trong file",
        "trang": [1]}})
    by_type = {"bao_dam_du_thau": [_p(1, "THƯ BẢO LÃNH... Phó giám đốc Phạm D")]}
    v = await SKILL.handler(by_type, None, {}, vision)
    assert v.ket_qua == KET_QUA_KHONG and "ủy quyền" in v.bang_chung


async def test_handler_ky_thay_guq_hop_le_dat():
    vision = ScriptedVision({"[RULE:chu_ky_bao_dam_uy_quyen]": {
        "ket_qua": "đạt", "nguoi_ky": "Phạm D", "chuc_danh": "Phó giám đốc",
        "co_uy_quyen": True, "bang_chung": "GUQ số 15: TGĐ ủy quyền PGĐ Phạm D ký bảo lãnh dự thầu",
        "trang": [1, 3], "do_tin": 0.85}})
    by_type = {"bao_dam_du_thau": [_p(1, "THƯ BẢO LÃNH... Phó giám đốc Phạm D"),
                                   _p(3, "GIẤY ỦY QUYỀN... ký thư bảo lãnh")]}
    v = await SKILL.handler(by_type, None, {}, vision)
    assert v.ket_qua == KET_QUA_DAT and v.trang == [1, 3]


async def test_handler_ai_error_becomes_loi():
    vision = ScriptedVision({})
    by_type = {"bao_dam_du_thau": [_p(1, "THƯ BẢO LÃNH")]}
    v = await SKILL.handler(by_type, None, {}, vision)
    assert v.ket_qua == KET_QUA_LOI
