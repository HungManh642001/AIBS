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


def _detail(ten, check_type, need=None):
    """Tiêu chí chi tiết hợp lệ; need != None -> đánh dấu thong_so._need (số còn thiếu)."""
    thong_so = {"_need": need} if need else {}
    return {
        "nhom": "hop_le", "ten": ten, "yeu_cau": "theo HSMT", "required_artifacts": [],
        "kieu": "pass_fail", "trong_so": 0.0,
        "sub_checks": [{"ten": f"kiểm {ten}", "check_type": check_type, "thong_so": thong_so,
                        "required_artifact": "", "blocking": True}],
        "proposed_artifacts": [],
    }


def _by_name(criteria, ten):
    return next(c for c in criteria if c["ten"] == ten)


async def test_critique_adds_missing_and_no_fabrication():
    """Recall guard: critique thêm tiêu chí sót. No-fab: thiếu số + KHÔNG có bằng chứng -> can_review."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _detail("Đơn dự thầu hợp lệ", "presence"),
        "[TAG:STRUCT:Bảo đảm dự thầu]": _detail("Bảo đảm dự thầu", "value_threshold",
                                                need="giá trị bảo đảm dự thầu (đồng)"),
        "[TAG:QUERY:Bảo đảm dự thầu]": {"queries": [
            {"ten": "kiểm Bảo đảm dự thầu", "query": "giá trị bảo đảm dự thầu"}]},
    })
    # retrieve rỗng -> không có bằng chứng -> không resolve -> _need còn -> can_review.
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.coverage.listed_n == 1
    assert gd.coverage.final_n == 2
    assert "Bảo đảm dự thầu" in gd.coverage.added_by_critique

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    ts = bd["sub_checks"][0]["thong_so"]
    assert ts["can_review"] is True  # KHÔNG bịa số
    assert "_need" not in ts  # marker đã được dọn
    assert any(n["ten"] == "Bảo đảm dự thầu" for n in gd.needs_review)

    # Tiêu chí không thiếu số -> không bị ép can_review.
    dd = _by_name(gd.criteria, "Đơn dự thầu hợp lệ")
    assert "can_review" not in dd["sub_checks"][0]["thong_so"]


async def test_evidence_present_resolves_no_review():
    """Thiếu số NHƯNG có bằng chứng -> sinh query, retrieve, resolve điền số (KHÔNG can_review)."""
    resolved = _detail("Bảo đảm dự thầu", "value_threshold")
    resolved["sub_checks"][0]["thong_so"] = {"value": 150000000, "days": 120}
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _detail("Bảo đảm dự thầu", "value_threshold",
                                                need="giá trị bảo đảm dự thầu"),
        "[TAG:QUERY:Bảo đảm dự thầu]": {"queries": [
            {"ten": "kiểm Bảo đảm dự thầu", "query": "giá trị bảo đảm dự thầu"}]},
        "[TAG:RESOLVE:Bảo đảm dự thầu]": resolved,
    })
    ev = [{"text": "Bảo đảm dự thầu 150 triệu, 120 ngày", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    gd = await wf.run(group=_GROUP)

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    ts = bd["sub_checks"][0]["thong_so"]
    assert ts.get("value") == 150000000
    assert "_need" not in ts and "can_review" not in ts
    assert gd.needs_review == []
    # Đã gọi đủ 3 lượt: STRUCT -> QUERY -> RESOLVE.
    assert any("[TAG:QUERY:Bảo đảm dự thầu]" in c for c in llm.calls)
    assert any("[TAG:RESOLVE:Bảo đảm dự thầu]" in c for c in llm.calls)


async def test_no_need_skips_query_and_resolve():
    """Structure không có _need -> bỏ qua sinh query & resolve (tiết kiệm call)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _detail("Đơn dự thầu hợp lệ", "presence"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.needs_review == []
    assert not any("[TAG:QUERY:" in c for c in llm.calls)
    assert not any("[TAG:RESOLVE:" in c for c in llm.calls)


async def test_detail_llm_error_marks_can_review():
    """Lỗi LLM structure 1 tiêu chí -> giữ tiêu chí + can_review + loi_ai (KHÔNG verdict bịa)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": RuntimeError("proxy down"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    assert c["can_review"] is True
    assert "proxy down" in c["loi_ai"]
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
        "[TAG:STRUCT:Thông số kỹ thuật]": _detail("Thông số kỹ thuật", "spec_match"),
    })
    ev = [{"text": "Yêu cầu kỹ thuật: công suất tối thiểu 10kW", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    await wf.run(group=group)

    list_call = next(c for c in llm.calls if "[TAG:LIST]" in c)
    assert "NỘI DUNG THAM CHIẾU PHẦN 4" in list_call
    assert "công suất tối thiểu 10kW" in list_call
