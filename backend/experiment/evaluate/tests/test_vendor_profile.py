from experiment.evaluate.schema import (
    HINH_THUC_DOC_LAP, HINH_THUC_KHONG_RO, HINH_THUC_LIEN_DANH,
    NGUON_HO_SO, NGUON_KHAI_BAO, NGUON_KHONG_DU_CAN_CU,
    PageRecord, VendorContext,
)
from experiment.evaluate.vendor_profile import canon_hinh_thuc, detect_vendor_profile
from experiment.evaluate.vision import ScriptedVision


def _page(loai, text="x", trang=1):
    return PageRecord(file=f"{loai}.pdf", trang=trang, loai_ho_so=loai, text=text)


def test_canon_hinh_thuc_maps_cli_tokens():
    assert canon_hinh_thuc("doc_lap") == HINH_THUC_DOC_LAP
    assert canon_hinh_thuc("Độc Lập") == HINH_THUC_DOC_LAP
    assert canon_hinh_thuc("lien-danh") == HINH_THUC_LIEN_DANH
    assert canon_hinh_thuc("liên danh") == HINH_THUC_LIEN_DANH
    assert canon_hinh_thuc("abc") == HINH_THUC_KHONG_RO      # không nhận diện -> KHÔNG đoán
    assert canon_hinh_thuc("") == HINH_THUC_KHONG_RO


async def test_detect_declared_wins_no_ai_call():
    """Khai báo ưu tiên tuyệt đối -> KHÔNG gọi AI."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("don_du_thau", "đơn")], v,
                                    vendor=VendorContext(ten="A", hinh_thuc="doc_lap"))
    assert p.hinh_thuc == HINH_THUC_DOC_LAP and p.nguon == NGUON_KHAI_BAO
    assert p.mau_thuan is False and p.do_tin == 1.0
    assert v.calls == []


async def test_detect_deterministic_from_lien_danh_file():
    """Có hồ sơ thỏa thuận liên danh -> liên danh TẤT ĐỊNH, 0 call."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("don_du_thau", "đơn"),
                                     _page("thoa_thuan_lien_danh", "TTLD")], v)
    assert p.hinh_thuc == HINH_THUC_LIEN_DANH and p.nguon == NGUON_HO_SO
    assert "thoa_thuan_lien_danh" in p.bang_chung and v.calls == []


async def test_detect_declared_lien_danh_with_file_no_conflict():
    """Khai liên danh + CÓ file -> nhất quán, không mâu thuẫn, 0 call."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("thoa_thuan_lien_danh", "TTLD")], v,
                                    vendor=VendorContext(ten="A", hinh_thuc="lien_danh"))
    assert p.hinh_thuc == HINH_THUC_LIEN_DANH and p.mau_thuan is False
    assert p.nguon == NGUON_KHAI_BAO and v.calls == []


async def test_detect_conflict_declared_doc_lap_but_has_lien_danh_file():
    """MÂU THUẪN -> fail-safe: 'không rõ' (KHÔNG gate) + cờ cảnh báo."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("thoa_thuan_lien_danh", "TTLD")], v,
                                    vendor=VendorContext(ten="A", hinh_thuc="doc_lap"))
    assert p.hinh_thuc == HINH_THUC_KHONG_RO and p.mau_thuan is True
    assert "khai báo" in p.ghi_chu and "thoa_thuan_lien_danh" in p.ghi_chu
    assert v.calls == []


async def test_detect_conflict_declared_lien_danh_but_no_file():
    """Khai liên danh mà KHÔNG có thỏa thuận -> mâu thuẫn -> không rõ (không gate).

    Nội dung TTLĐ sẽ chạy tiếp và ra 'thiếu hồ sơ' — đó là PHÁT HIỆN THẬT, không được N/A đi.
    """
    p = await detect_vendor_profile([_page("don_du_thau", "đơn")], ScriptedVision({}),
                                    vendor=VendorContext(ten="A", hinh_thuc="lien_danh"))
    assert p.hinh_thuc == HINH_THUC_KHONG_RO and p.mau_thuan is True


async def test_detect_no_evidence_returns_khong_ro_no_call():
    """Không đơn dự thầu, không TTLĐ, không khai báo -> không đủ căn cứ, 0 call."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("bao_dam_du_thau", "thư")], v)
    assert p.hinh_thuc == HINH_THUC_KHONG_RO and p.nguon == NGUON_KHONG_DU_CAN_CU
    assert v.calls == []


async def test_detect_from_don_du_thau_via_llm():
    """Không khai báo, không TTLĐ, có đơn -> 1 call text-only đọc đơn."""
    from experiment.evaluate.schema import NGUON_DON_DU_THAU

    v = ScriptedVision({"[VENDOR_FORM]": {"hinh_thuc": "liên danh",
                                          "bang_chung": "Chúng tôi, liên danh A-B, ...",
                                          "trang": [1], "do_tin": 0.9}})
    p = await detect_vendor_profile([_page("don_du_thau", "liên danh A-B")], v)
    assert p.hinh_thuc == HINH_THUC_LIEN_DANH and p.nguon == NGUON_DON_DU_THAU
    assert p.trang == [1] and p.do_tin == 0.9
    assert len(v.calls) == 1 and v.calls[0][1] == 0        # text-only, KHÔNG đính ảnh


async def test_detect_llm_low_confidence_is_khong_ro():
    """do_tin < 0.7 -> KHÔNG dám gate -> 'không rõ' (no-fab)."""
    v = ScriptedVision({"[VENDOR_FORM]": {"hinh_thuc": "độc lập", "do_tin": 0.4}})
    p = await detect_vendor_profile([_page("don_du_thau", "mơ hồ")], v)
    assert p.hinh_thuc == HINH_THUC_KHONG_RO and "độ tin" in p.ghi_chu


async def test_detect_llm_error_is_khong_ro_not_guess():
    """AI lỗi -> 'không rõ', KHÔNG đoán."""
    v = ScriptedVision({})            # không khớp key -> AiOutcome(status="error")
    p = await detect_vendor_profile([_page("don_du_thau", "đơn")], v)
    assert p.hinh_thuc == HINH_THUC_KHONG_RO and "AI lỗi" in p.ghi_chu


async def test_detect_llm_unparseable_form_is_khong_ro():
    """AI trả hình thức không canon được -> 'không rõ'."""
    v = ScriptedVision({"[VENDOR_FORM]": {"hinh_thuc": "chưa rõ", "do_tin": 0.9}})
    p = await detect_vendor_profile([_page("don_du_thau", "x")], v)
    assert p.hinh_thuc == HINH_THUC_KHONG_RO


def test_vendor_form_prompt_tag_does_not_collide():
    """Prompt dò hình thức KHÔNG được chứa tag của ingest/eval/rule (ScriptedVision first-match)."""
    from experiment.evaluate.prompts import SYS_VENDOR_FORM, vendor_form_prompt

    hay = f"{SYS_VENDOR_FORM}\n{vendor_form_prompt('đơn', VendorContext(ten='ABC'))}"
    assert "[VENDOR_FORM]" in hay and "ABC" in hay
    assert "[IN]" not in hay and "[EV:" not in hay and "[RULE:" not in hay


async def test_detect_vendor_without_declaration_is_not_conflict():
    """VendorContext có tên nhưng KHÔNG khai hình thức -> không phải mâu thuẫn, dò tiếp."""
    v = ScriptedVision({})
    p = await detect_vendor_profile([_page("thoa_thuan_lien_danh", "TTLD")], v,
                                    vendor=VendorContext(ten="A"))
    assert p.hinh_thuc == HINH_THUC_LIEN_DANH and p.mau_thuan is False
