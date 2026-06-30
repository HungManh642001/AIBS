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

# Nhóm có BẢNG -> critique được bật (chống sót cho nơi liệt kê 1 lượt dễ sót dòng).
_TABLE_GROUP = {
    "group": "nang_luc",
    "muc": "Mục 2. Năng lực và kinh nghiệm",
    "is_reference": False,
    "ref_target": None,
    "blocks": [{"type": "table", "page": [30, 30],
                "rows": [["TT", "Mô tả", "Yêu cầu"], ["1", "Bảo đảm dự thầu", "theo BDS"]]}],
}


def _nd(noi_dung, yeu_cau="", can_tra_cuu=True, kieu="đối chiếu"):
    return {"noi_dung": noi_dung, "yeu_cau": yeu_cau, "can_tra_cuu": can_tra_cuu, "kieu_check": kieu}


def _crit(ten, contents, nhom="hop_le", tien_quyet=False, hsdt=None):
    return {
        "nhom": nhom, "ten": ten, "yeu_cau_goc": f"{ten} theo HSMT",
        "hsdt_can_kiem_tra": hsdt or [], "tien_quyet": tien_quyet,
        "noi_dung_can_kiem_tra": contents,
    }


def _by_name(criteria, ten):
    return next(c for c in criteria if c["ten"] == ten)


def _nd_by(crit, noi_dung):
    return next(n for n in crit["noi_dung_can_kiem_tra"] if n["noi_dung"] == noi_dung)


async def test_critique_adds_missing_and_no_fabrication():
    """Recall guard (nhóm bảng): critique thêm tiêu chí sót. No-fab: can_tra_cuu không ra -> can_review."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "nang_luc", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": [{"nhom": "nang_luc", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", yeu_cau="phải có", can_tra_cuu=False,
                                       kieu="tồn tại")], nhom="nang_luc"),
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh")], nhom="nang_luc"),  # can_tra_cuu, trống
    })
    # retrieve rỗng -> không bằng chứng -> không resolve -> yeu_cau vẫn trống -> can_review.
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_TABLE_GROUP)

    assert gd.coverage.listed_n == 1
    assert gd.coverage.final_n == 2
    assert "Bảo đảm dự thầu" in gd.coverage.added_by_critique

    bd = _nd_by(_by_name(gd.criteria, "Bảo đảm dự thầu"), "Giá trị bảo lãnh")
    assert bd["can_review"] is True  # KHÔNG bịa số
    assert not bd["yeu_cau"]
    assert any(n["ten"] == "Bảo đảm dự thầu" for n in gd.needs_review)

    # Nội dung không cần tra cứu -> không bị ép can_review.
    dd = _nd_by(_by_name(gd.criteria, "Đơn dự thầu hợp lệ"), "Có đơn dự thầu")
    assert dd["can_review"] is False


async def test_critique_skipped_for_free_text():
    """Nhóm free-text (không bảng) -> KHÔNG gọi critique (tránh lan man)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", yeu_cau="phải có", can_tra_cuu=False)]),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert not any("[TAG:CRITIQUE]" in c for c in llm.calls)
    assert gd.coverage.added_by_critique == []
    assert gd.coverage.final_n == 1


async def test_search_per_need_independent_resolve():
    """Mỗi need search ĐỘC LẬP: query+resolve riêng từng need, điền đúng giá trị (không nhiễu chéo)."""
    captured: list[str] = []

    def retrieve_fn(q, k=5):
        captured.append(q)
        if "hiệu lực" in q:
            return [{"text": "Thời hạn hiệu lực bảo lãnh: 120 ngày", "metadata": {}, "score": 1.0}]
        return [{"text": "Giá trị bảo đảm dự thầu: 6.100.000 VNĐ", "metadata": {}, "score": 1.0}]

    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh"), _nd("Thời gian hiệu lực")]),
        "[TAG:QUERY:Giá trị bảo lãnh]": {"query": "giá trị bảo đảm dự thầu"},
        "[TAG:QUERY:Thời gian hiệu lực]": {"query": "thời gian hiệu lực bảo lãnh"},
        "[TAG:RESOLVE:Giá trị bảo lãnh]": {"yeu_cau": "6.100.000 VNĐ", "can_review": False},
        "[TAG:RESOLVE:Thời gian hiệu lực]": {"yeu_cau": ">= 120 ngày", "can_review": False},
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    c = _by_name(gd.criteria, "Bảo đảm dự thầu")
    assert _nd_by(c, "Giá trị bảo lãnh")["yeu_cau"] == "6.100.000 VNĐ"
    assert _nd_by(c, "Thời gian hiệu lực")["yeu_cau"] == ">= 120 ngày"
    assert gd.needs_review == []
    # Mỗi need retrieve RIÊNG -> 2 lượt truy hồi độc lập.
    assert len(captured) == 2
    # Mỗi need có lượt RESOLVE riêng (1 call 1 việc).
    assert sum("[TAG:RESOLVE:" in c for c in llm.calls) == 2


async def test_no_lookup_item_not_searched_or_flagged():
    """Nội dung can_tra_cuu=false (kiểm tồn tại/điều kiện) -> KHÔNG tra cứu, KHÔNG can_review."""
    captured: list[str] = []
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Thời gian ký đơn"}]},
        "[TAG:STRUCT:Thời gian ký đơn]": _crit("Thời gian ký đơn", [
            _nd("Thời điểm phát hành HSMT", can_tra_cuu=True),
            _nd("Ngày ký đơn dự thầu", yeu_cau="sau thời điểm phát hành HSMT",
                can_tra_cuu=False, kieu="so sánh ngày"),
        ]),
        "[TAG:QUERY:Thời điểm phát hành HSMT]": {"query": "thời điểm phát hành hồ sơ mời thầu"},
        "[TAG:RESOLVE:Thời điểm phát hành HSMT]": {"yeu_cau": "04/06/2025", "can_review": False},
    })

    def retrieve_fn(q, k=5):
        captured.append(q)
        return [{"text": "HSMT phát hành ngày 04/06/2025", "metadata": {}, "score": 1.0}]

    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    assert _nd_by(c, "Thời điểm phát hành HSMT")["yeu_cau"] == "04/06/2025"
    nb = _nd_by(c, "Ngày ký đơn dự thầu")
    assert nb["can_review"] is False  # can_tra_cuu=false -> không bao giờ bị flag
    assert nb["yeu_cau"] == "sau thời điểm phát hành HSMT"  # giữ nguyên điều kiện
    assert gd.needs_review == []
    # CHỈ truy hồi nội dung can_tra_cuu=true.
    assert captured == ["thời điểm phát hành hồ sơ mời thầu"]


async def test_no_need_skips_search():
    """Không có nội dung can_tra_cuu -> bỏ qua query & resolve."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", yeu_cau="phải có", can_tra_cuu=False)]),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert gd.needs_review == []
    assert not any("[TAG:QUERY:" in c for c in llm.calls)
    assert not any("[TAG:RESOLVE:" in c for c in llm.calls)


async def test_analyze_llm_error_marks_loi_ai():
    """Lỗi LLM analyze 1 tiêu chí -> giữ tiêu chí + loi_ai (KHÔNG verdict bịa)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": RuntimeError("proxy down"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    assert "proxy down" in c["loi_ai"]
    assert c["noi_dung_can_kiem_tra"] == []
    assert gd.needs_review


async def test_reference_following_injects_phan4():
    """Mục 3 is_reference -> nguồn cấp cho LLM (step list) phải chứa nội dung Phần 4 (đã retrieve)."""
    group = {
        "group": "ky_thuat", "muc": "Mục 3. Tiêu chuẩn kỹ thuật",
        "is_reference": True, "ref_target": {"kind": "phan", "number": "4"},
        "blocks": [{"type": "text", "page": [40, 40], "text": "Theo Phần 4."}],
    }
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "ky_thuat", "ten": "Thông số kỹ thuật"}]},
        "[TAG:STRUCT:Thông số kỹ thuật]": _crit(
            "Thông số kỹ thuật", [_nd("Đáp ứng yêu cầu kỹ thuật", yeu_cau="theo Phần 4",
                                      can_tra_cuu=False)], nhom="ky_thuat"),
    })
    ev = [{"text": "Yêu cầu kỹ thuật: công suất tối thiểu 10kW", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5: ev, timeout=30)
    await wf.run(group=group)

    list_call = next(c for c in llm.calls if "[TAG:LIST]" in c)
    assert "NỘI DUNG THAM CHIẾU PHẦN 4" in list_call
    assert "công suất tối thiểu 10kW" in list_call
