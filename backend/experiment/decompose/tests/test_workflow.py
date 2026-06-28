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


def _detail(ten, check_type):
    return {
        "nhom": "hop_le", "ten": ten, "yeu_cau": "theo HSMT", "required_artifacts": [],
        "kieu": "pass_fail", "trong_so": 0.0,
        "sub_checks": [{"ten": f"kiểm {ten}", "check_type": check_type, "thong_so": {},
                        "required_artifact": "", "blocking": True}],
        "proposed_artifacts": [],
    }


def _by_name(criteria, ten):
    return next(c for c in criteria if c["ten"] == ten)


async def test_critique_adds_missing_and_no_fabrication():
    """Recall guard: critique thêm tiêu chí sót. No-fab: thiếu bằng chứng -> can_review."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:DETAIL:Đơn dự thầu hợp lệ]": _detail("Đơn dự thầu hợp lệ", "presence"),
        "[TAG:DETAIL:Bảo đảm dự thầu]": _detail("Bảo đảm dự thầu", "value_threshold"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.coverage.listed_n == 1
    assert gd.coverage.final_n == 2
    assert "Bảo đảm dự thầu" in gd.coverage.added_by_critique

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    assert bd["sub_checks"][0]["thong_so"]["can_review"] is True  # KHÔNG bịa số
    assert any(n["ten"] == "Bảo đảm dự thầu" for n in gd.needs_review)


async def test_evidence_present_no_forced_review():
    """Có bằng chứng -> KHÔNG ép can_review (để LLM tự quyết)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:DETAIL:Bảo đảm dự thầu]": _detail("Bảo đảm dự thầu", "value_threshold"),
    })
    ev = [{"text": "Bảo đảm dự thầu 150 triệu, 120 ngày", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    gd = await wf.run(group=_GROUP)

    bd = _by_name(gd.criteria, "Bảo đảm dự thầu")
    assert "can_review" not in bd["sub_checks"][0]["thong_so"]
    assert gd.needs_review == []


async def test_detail_llm_error_marks_can_review():
    """Lỗi LLM 1 tiêu chí -> giữ tiêu chí + can_review + loi_ai (KHÔNG verdict bịa)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": []},
        "[TAG:DETAIL:Đơn dự thầu hợp lệ]": RuntimeError("proxy down"),
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
        "[TAG:DETAIL:Thông số kỹ thuật]": _detail("Thông số kỹ thuật", "spec_match"),
    })
    ev = [{"text": "Yêu cầu kỹ thuật: công suất tối thiểu 10kW", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    await wf.run(group=group)

    list_call = next(c for c in llm.calls if "[TAG:LIST]" in c)
    assert "NỘI DUNG THAM CHIẾU PHẦN 4" in list_call
    assert "công suất tối thiểu 10kW" in list_call
