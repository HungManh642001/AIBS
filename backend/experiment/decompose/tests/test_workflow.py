from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.workflow import DecomposeWorkflow

_GROUP = {
    "group": "hop_le",
    "muc": "Mục 1. Đánh giá tính hợp lệ",
    "is_reference": False,
    "ref_target": None,
    "blocks": [{"type": "text", "page": [27, 27],
                "text": "E-HSDT hợp lệ khi có đơn dự thầu và bảo đảm dự thầu hợp lệ."}],
}


def _nd(ten, gia_tri="", nguon="hsmt", kieu="đối chiếu"):
    return {"ten": ten, "gia_tri": gia_tri, "nguon": nguon, "kieu_check": kieu}


def _crit(ten, contents, nhom="hop_le", tien_quyet=False, hsdt=None):
    return {
        "nhom": nhom, "ten": ten, "yeu_cau_goc": f"{ten} theo HSMT",
        "hsdt_can_kiem_tra": hsdt or [], "tien_quyet": tien_quyet,
        "noi_dung_can_kiem_tra": contents,
    }


def _by_name(criteria, ten):
    return next(c for c in criteria if c["ten"] == ten)


async def test_critique_adds_missing_and_no_fabrication():
    """Recall guard: critique thêm tiêu chí sót. No-fab: nội dung hsmt không tra được -> can_review."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", nguon="hsdt", kieu="tồn tại")]),
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh")]),  # nguon=hsmt, gia_tri trống
        "[TAG:QUERY:Bảo đảm dự thầu]": {"queries": [
            {"ten": "Giá trị bảo lãnh", "query": "giá trị bảo đảm dự thầu"}]},
    })
    # retrieve rỗng -> không bằng chứng -> không resolve -> gia_tri vẫn trống -> can_review.
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.coverage.listed_n == 1
    assert gd.coverage.final_n == 2
    assert "Bảo đảm dự thầu" in gd.coverage.added_by_critique

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    nd = bd["noi_dung_can_kiem_tra"][0]
    assert nd["can_review"] is True  # KHÔNG bịa số
    assert not nd["gia_tri"]
    assert any(n["ten"] == "Bảo đảm dự thầu" for n in gd.needs_review)

    # Nội dung phía HSDT -> không bị ép can_review.
    dd = _by_name(gd.criteria, "Đơn dự thầu hợp lệ")
    assert dd["noi_dung_can_kiem_tra"][0]["can_review"] is False


async def test_evidence_present_resolves_no_review():
    """Thiếu giá trị NHƯNG có bằng chứng -> sinh query, retrieve, resolve điền gia_tri (KHÔNG can_review)."""
    resolved = _crit("Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh", gia_tri="6.100.000 VNĐ")])
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit("Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh")]),
        "[TAG:QUERY:Bảo đảm dự thầu]": {"queries": [
            {"ten": "Giá trị bảo lãnh", "query": "giá trị bảo đảm dự thầu"}]},
        "[TAG:RESOLVE:Bảo đảm dự thầu]": resolved,
    })
    ev = [{"text": "Giá trị bảo đảm dự thầu: 6.100.000 VNĐ", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    gd = await wf.run(group=_GROUP)

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    nd = bd["noi_dung_can_kiem_tra"][0]
    assert nd["gia_tri"] == "6.100.000 VNĐ"
    assert nd["can_review"] is False
    assert gd.needs_review == []
    assert any("[TAG:QUERY:Bảo đảm dự thầu]" in c for c in llm.calls)
    assert any("[TAG:RESOLVE:Bảo đảm dự thầu]" in c for c in llm.calls)


async def test_hsdt_content_deferred_not_can_review():
    """Phân biệt nguồn: hsmt thiếu -> tra/điền; hsdt -> đánh giá sau, KHÔNG tra/can_review."""
    struct = _crit(
        "Thời gian ký đơn sau phát hành HSMT",
        [
            _nd("Thời điểm phát hành HSMT", nguon="hsmt"),
            _nd("Ngày ký đơn dự thầu", gia_tri="sau thời điểm phát hành HSMT",
                nguon="hsdt", kieu="so sánh ngày"),
        ],
    )
    resolved = _crit(
        "Thời gian ký đơn sau phát hành HSMT",
        [
            _nd("Thời điểm phát hành HSMT", gia_tri="04/06/2025", nguon="hsmt"),
            _nd("Ngày ký đơn dự thầu", gia_tri="sau thời điểm phát hành HSMT",
                nguon="hsdt", kieu="so sánh ngày"),
        ],
    )
    captured: list[str] = []

    def retrieve_fn(q, k=5):
        captured.append(q)
        return [{"text": "HSMT phát hành ngày 04/06/2025", "metadata": {}, "score": 1.0}]

    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [
            {"nhom": "hop_le", "ten": "Thời gian ký đơn sau phát hành HSMT"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:": struct,
        "[TAG:QUERY:": {"queries": [
            {"ten": "Thời điểm phát hành HSMT", "query": "thời điểm phát hành hồ sơ mời thầu"}]},
        "[TAG:RESOLVE:": resolved,
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    nds = {n["ten"]: n for n in c["noi_dung_can_kiem_tra"]}
    # HSMT: resolve điền giá trị, không can_review.
    assert nds["Thời điểm phát hành HSMT"]["gia_tri"] == "04/06/2025"
    assert nds["Thời điểm phát hành HSMT"]["can_review"] is False
    # HSDT: đánh giá sau, KHÔNG can_review.
    assert nds["Ngày ký đơn dự thầu"]["nguon"] == "hsdt"
    assert nds["Ngày ký đơn dự thầu"]["can_review"] is False
    assert gd.needs_review == []
    # Chỉ truy hồi nội dung HSMT.
    assert captured == ["thời điểm phát hành hồ sơ mời thầu"]


async def test_no_need_skips_query_and_resolve():
    """Không có nội dung hsmt thiếu giá trị -> bỏ qua sinh query & resolve (tiết kiệm call)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", nguon="hsdt", kieu="tồn tại")]),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.needs_review == []
    assert not any("[TAG:QUERY:" in c for c in llm.calls)
    assert not any("[TAG:RESOLVE:" in c for c in llm.calls)


async def test_detail_llm_error_marks_loi_ai():
    """Lỗi LLM structure 1 tiêu chí -> giữ tiêu chí + loi_ai (KHÔNG verdict bịa)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": RuntimeError("proxy down"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    assert "proxy down" in c["loi_ai"]
    assert c["noi_dung_can_kiem_tra"] == []
    assert gd.needs_review


async def test_reference_following_injects_phan4():
    """Mục 3 is_reference -> nguồn cấp cho LLM phải chứa nội dung Phần 4 (đã retrieve)."""
    group = {
        "group": "ky_thuat", "muc": "Mục 3. Tiêu chuẩn kỹ thuật",
        "is_reference": True, "ref_target": {"kind": "phan", "number": "4"},
        "blocks": [{"type": "text", "page": [40, 40], "text": "Theo Phần 4."}],
    }
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "ky_thuat", "ten": "Thông số kỹ thuật"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Thông số kỹ thuật]": _crit(
            "Thông số kỹ thuật", [_nd("Đáp ứng yêu cầu kỹ thuật", nguon="hsdt", kieu="đối chiếu")],
            nhom="ky_thuat"),
    })
    ev = [{"text": "Yêu cầu kỹ thuật: công suất tối thiểu 10kW", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    await wf.run(group=group)

    list_call = next(c for c in llm.calls if "[TAG:LIST]" in c)
    assert "NỘI DUNG THAM CHIẾU PHẦN 4" in list_call
    assert "công suất tối thiểu 10kW" in list_call
