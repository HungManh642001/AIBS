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


def _nd(noi_dung, yeu_cau="theo HSMT", can_lam_ro="", hsdt="don_du_thau"):
    """Item noi_dung_can_kiem_tra. can_lam_ro != '' -> cần tra cứu (step 3 tra)."""
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": hsdt, "yeu_cau": yeu_cau,
            "can_lam_ro": can_lam_ro, "can_tra_cuu": bool(can_lam_ro)}


def _crit(ten, contents, nhom="hop_le", tien_quyet=False, hsdt=None):
    return {
        "nhom": nhom, "ten": ten, "yeu_cau_goc": f"{ten} theo HSMT",
        "hsdt_can_kiem_tra": hsdt or [], "tien_quyet": tien_quyet,
        "noi_dung_can_kiem_tra": contents,
    }


def _by_name(criteria, ten):
    return next(c for c in criteria if c["ten"] == ten)


def _nd_by(crit, noi_dung):
    return next(n for n in crit["noi_dung_can_kiem_tra"] if n["noi_dung_kiem_tra"] == noi_dung)


async def test_critique_adds_missing_and_no_fabrication():
    """Recall guard (nhóm bảng): critique thêm tiêu chí sót. No-fab: tra không ra -> can_review."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "nang_luc", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:CRITIQUE]": {"criteria": [{"nhom": "nang_luc", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", yeu_cau="phải có đơn")],
            nhom="nang_luc"),
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh", can_lam_ro="Giá trị bảo lãnh")], nhom="nang_luc"),
    })
    # retrieve rỗng -> không bằng chứng -> không resolve -> thong_tin_bo_sung trống -> can_review.
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5, clause_doc=None: [], timeout=30)
    gd = await wf.run(group=_TABLE_GROUP)

    assert gd.coverage.listed_n == 1
    assert gd.coverage.final_n == 2
    assert "Bảo đảm dự thầu" in gd.coverage.added_by_critique

    bd = _nd_by(_by_name(gd.criteria, "Bảo đảm dự thầu"), "Giá trị bảo lãnh")
    assert bd["can_review"] is True  # KHÔNG bịa
    assert not bd["thong_tin_bo_sung"]
    assert bd["yeu_cau"] == "theo HSMT"  # yêu cầu (luật) giữ nguyên, KHÔNG bị ghi đè
    assert any(n["ten"] == "Bảo đảm dự thầu" for n in gd.needs_review)

    # Nội dung không cần tra cứu -> không bị ép can_review.
    dd = _nd_by(_by_name(gd.criteria, "Đơn dự thầu hợp lệ"), "Có đơn dự thầu")
    assert dd["can_review"] is False


async def test_critique_skipped_for_free_text():
    """Nhóm free-text (không bảng) -> KHÔNG gọi critique (tránh lan man)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": _crit(
            "Đơn dự thầu hợp lệ", [_nd("Có đơn dự thầu", yeu_cau="phải có")]),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5, clause_doc=None: [], timeout=30)
    gd = await wf.run(group=_GROUP)

    assert not any("[TAG:CRITIQUE]" in c for c in llm.calls)
    assert gd.coverage.added_by_critique == []
    assert gd.coverage.final_n == 1


async def test_search_per_need_independent_resolve():
    """Mỗi need search ĐỘC LẬP: điền thong_tin_bo_sung + nguon riêng từng need (không nhiễu chéo)."""
    captured: list[tuple] = []

    def retrieve_fn(q, k=5, clause_doc=None):
        captured.append((q, clause_doc))
        if "hiệu lực" in q:
            return [{"text": "E-CDNT 18.2 | hiệu lực bảo lãnh 120 ngày",
                     "metadata": {"chunk_id": "h", "clause_id": "18.2", "clause_doc": "bdl"}, "score": 1.0}]
        return [{"text": "E-CDNT 18.2 | Giá trị bảo đảm 6.100.000 VNĐ",
                 "metadata": {"chunk_id": "g", "clause_id": "18.2", "clause_doc": "bdl"}, "score": 1.0}]

    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Bảo đảm dự thầu]": _crit(
            "Bảo đảm dự thầu",
            [_nd("Giá trị bảo lãnh", can_lam_ro="Giá trị bảo lãnh", hsdt=""),
             _nd("Thời gian hiệu lực", can_lam_ro="Thời gian hiệu lực bảo lãnh", hsdt="")],
            hsdt=["bao_lanh_du_thau"]),
        "[TAG:QUERY:Giá trị bảo lãnh]": {"query": "giá trị bảo đảm dự thầu"},
        "[TAG:QUERY:Thời gian hiệu lực]": {"query": "thời gian hiệu lực bảo lãnh"},
        "[TAG:RESOLVE:Giá trị bảo lãnh]":
            {"thong_tin_bo_sung": "Giá trị bảo lãnh: 6.100.000 VNĐ", "nguon": "E-BDL 18.2", "can_review": False},
        "[TAG:RESOLVE:Thời gian hiệu lực]":
            {"thong_tin_bo_sung": "Thời gian hiệu lực: ≥ 120 ngày", "nguon": "", "can_review": False},
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    c = _by_name(gd.criteria, "Bảo đảm dự thầu")
    gv = _nd_by(c, "Giá trị bảo lãnh")
    hl = _nd_by(c, "Thời gian hiệu lực")
    assert gv["thong_tin_bo_sung"] == "Giá trị bảo lãnh: 6.100.000 VNĐ"
    assert gv["nguon"] == "E-BDL 18.2"
    assert hl["thong_tin_bo_sung"] == "Thời gian hiệu lực: ≥ 120 ngày"
    assert hl["nguon"] == "E-BDL 18.2"   # nguon rỗng -> backfill từ clause_id của hit
    # hsdt_kiem_tra được bù per item từ hsdt_can_kiem_tra của tiêu chí.
    assert gv["hsdt_kiem_tra"] == "bao_lanh_du_thau"
    assert gd.needs_review == []
    assert sum("[TAG:RESOLVE:" in c for c in llm.calls) == 2
    assert sum(1 for _, cd in captured if cd == "bdl") == 2  # mỗi need 1 lượt tra E-BDL


async def test_search_query_anchored_with_clause_ref():
    """Neo mã điều khoản: query truy hồi chứa mã (18.3 + 18) trích từ yeu_cau_goc + thiên vị E-BDL."""
    captured: list[str] = []

    def retrieve_fn(q, k=5, clause_doc=None):
        captured.append(q)
        return [{"text": "E-CDNT 18.2 | Giá trị bảo đảm: 6.100.000 VNĐ",
                 "metadata": {"chunk_id": "g", "clause_id": "18.2", "clause_doc": "bdl"}, "score": 1.0}]

    struct = _crit("Bảo đảm dự thầu", [_nd("Giá trị bảo lãnh", can_lam_ro="Giá trị bảo lãnh")])
    struct["yeu_cau_goc"] = "Bảo đảm dự thầu không vi phạm Mục 18.3 E-CDNT"
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Bảo đảm dự thầu"}]},
        "[TAG:STRUCT:Bảo đảm dự thầu]": struct,
        "[TAG:QUERY:Giá trị bảo lãnh]": {"query": "giá trị bảo đảm dự thầu"},
        "[TAG:RESOLVE:Giá trị bảo lãnh]":
            {"thong_tin_bo_sung": "Giá trị: 6.100.000 VNĐ", "nguon": "E-BDL 18.2", "can_review": False},
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    await wf.run(group=_GROUP)

    q = captured[0]
    assert "18.3" in q and " 18 " in f" {q} "   # mã đầy đủ + mã lớn
    assert "giá trị bảo đảm dự thầu" in q        # giữ query ngữ nghĩa từ LLM
    assert "bảng dữ liệu" in q.lower()           # thiên vị mục dữ liệu


async def test_no_lookup_item_not_searched_or_flagged():
    """Nội dung không cần làm rõ (can_tra_cuu=false) -> KHÔNG tra cứu, KHÔNG can_review."""
    captured: list[str] = []
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Thời gian ký đơn"}]},
        "[TAG:STRUCT:Thời gian ký đơn]": _crit("Thời gian ký đơn", [
            _nd("Thời điểm phát hành HSMT", can_lam_ro="Thời điểm phát hành HSMT"),
            _nd("Ngày ký đơn dự thầu", yeu_cau="sau thời điểm phát hành HSMT"),
        ]),
        "[TAG:QUERY:Thời điểm phát hành HSMT]": {"query": "thời điểm phát hành hồ sơ mời thầu"},
        "[TAG:RESOLVE:Thời điểm phát hành HSMT]":
            {"thong_tin_bo_sung": "Phát hành: 04/06/2025", "nguon": "E-BDL 1.1", "can_review": False},
    })

    def retrieve_fn(q, k=5, clause_doc=None):
        captured.append(q)
        return [{"text": "E-CDNT 1.1 | HSMT phát hành 04/06/2025",
                 "metadata": {"chunk_id": "p", "clause_id": "1.1", "clause_doc": "bdl"}, "score": 1.0}]

    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30)
    gd = await wf.run(group=_GROUP)

    c = gd.criteria[0]
    assert _nd_by(c, "Thời điểm phát hành HSMT")["thong_tin_bo_sung"] == "Phát hành: 04/06/2025"
    nb = _nd_by(c, "Ngày ký đơn dự thầu")
    assert nb["can_review"] is False           # không cần làm rõ -> không bao giờ flag
    assert nb["yeu_cau"] == "sau thời điểm phát hành HSMT"
    assert gd.needs_review == []
    # CHỈ truy hồi nội dung cần làm rõ (2 lượt: E-BDL + tra chung); KHÔNG tra "ngày ký đơn".
    assert len(captured) == 2
    assert all("thời điểm phát hành hồ sơ mời thầu" in q for q in captured)
    assert not any("ngày ký đơn" in q for q in captured)


async def test_analyze_llm_error_marks_loi_ai():
    """Lỗi LLM analyze 1 tiêu chí -> giữ tiêu chí + loi_ai (KHÔNG verdict bịa)."""
    llm = ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ"}]},
        "[TAG:STRUCT:Đơn dự thầu hợp lệ]": RuntimeError("proxy down"),
    })
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5, clause_doc=None: [], timeout=30)
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
            "Thông số kỹ thuật", [_nd("Đáp ứng yêu cầu kỹ thuật", yeu_cau="theo Phần 4")],
            nhom="ky_thuat"),
    })
    ev = [{"text": "Yêu cầu kỹ thuật: công suất tối thiểu 10kW", "metadata": {}, "score": 1.0}]
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=lambda q, k=5, clause_doc=None: ev, timeout=30)
    await wf.run(group=group)

    list_call = next(c for c in llm.calls if "[TAG:LIST]" in c)
    assert "NỘI DUNG THAM CHIẾU PHẦN 4" in list_call
    assert "công suất tối thiểu 10kW" in list_call
