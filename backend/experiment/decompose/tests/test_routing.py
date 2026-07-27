"""Route theo nguồn tài liệu (step 3): schema + prompt + workflow."""
from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.prompts import query_prompt
from experiment.decompose.schema import validate_query
from experiment.decompose.workflow import DecomposeWorkflow


def test_validate_query_accepts_nguon_goi_y():
    out = validate_query({"query": "q", "nguon_goi_y": ["tbmt"]})
    assert out["nguon_goi_y"] == ["tbmt"]
    # thiếu field -> mặc định [] (script cũ chỉ trả {"query"} vẫn chạy)
    assert validate_query({"query": "q"})["nguon_goi_y"] == []


def test_validate_query_unwraps_nested_result():
    """Qwen đôi khi bọc JSON trong khóa con (cot_block 'lý do TRƯỚC result') -> mở gói."""
    out = validate_query({"ly_do": "x", "result": {"query": "thời điểm đóng thầu", "nguon_goi_y": ["tbmt"]}})
    assert out["query"] == "thời điểm đóng thầu"
    assert out["nguon_goi_y"] == ["tbmt"]
    # top-level có query -> KHÔNG mở gói (giữ nguyên hành vi cũ)
    assert validate_query({"query": "q", "result": {"query": "khac"}})["query"] == "q"
    # không đâu có query -> giữ default rỗng (fallback ở workflow lo)
    assert validate_query({"ly_do": "x"})["query"] == ""


def test_query_prompt_with_sources_lists_catalog():
    p = query_prompt(
        {"ten": "Thời điểm đóng thầu"},
        {"noi_dung_kiem_tra": "Thời điểm đóng thầu", "can_lam_ro": "Thời điểm đóng thầu"},
        sources={"hsmt": "Hồ sơ mời thầu chính", "tbmt": "Thông báo mời thầu: thời gian phát hành/đóng/mở thầu"},
    )
    assert "[TAG:QUERY:Thời điểm đóng thầu]" in p          # tag giữ nguyên (ScriptedLlm khớp)
    assert "tbmt: Thông báo mời thầu" in p                  # danh mục nguồn có mặt
    assert "nguon_goi_y" in p                               # schema mở rộng


def test_sys_query_flat_no_hard_schema():
    """SYS_QUERY không chốt cứng schema (xung đột nguon_goi_y đa nguồn) + cấm bọc khóa con."""
    from experiment.decompose.prompts import SYS_QUERY
    assert '{"query":"..."}' not in SYS_QUERY
    assert "PHẲNG" in SYS_QUERY and "result" in SYS_QUERY


def test_struct_prompt_teaches_hsdt_side_rule():
    """SYS_STRUCT phân biệt thông tin phía mời thầu vs nội dung hồ sơ nhà thầu (VÍ DỤ 3 negative)."""
    from experiment.decompose.prompts import SYS_STRUCT, struct_prompt

    assert "hồ sơ nhà thầu" in SYS_STRUCT.lower() or "hồ sơ nhà thầu" in SYS_STRUCT
    p = struct_prompt({"ten": "Thỏa thuận liên danh", "nhom": "hop_le"})
    assert "VÍ DỤ 3" in p and "thỏa thuận liên danh" in p.lower()
    assert '"can_tra_cuu":false' in p.replace(" ", "")      # ví dụ negative: KHÔNG tra cứu


def test_sys_struct_teaches_ap_dung_per_noidung():
    """ap_dung ở CẤP NỘI DUNG: mệnh đề điều kiện liên danh -> 'lien_danh'; chung -> '' (mặc định).

    VÍ DỤ 3 (trộn) phải dạy tách nội dung chung (ap_dung='') và nội dung liên danh (ap_dung='lien_danh').
    """
    from experiment.decompose.prompts import SYS_STRUCT, struct_prompt

    low = SYS_STRUCT.lower()
    assert "ap_dung" in SYS_STRUCT and "lien_danh" in SYS_STRUCT
    assert "mọi nhà thầu" in low                       # mặc định '' = mọi nhà thầu
    p = struct_prompt({"ten": "Đơn dự thầu", "nhom": "hop_le"})
    assert '"ap_dung":"lien_danh"' in p.replace(" ", "") and '"ap_dung":""' in p.replace(" ", "")


def test_validate_criterion_keeps_ap_dung():
    from experiment.decompose.schema import validate_criterion

    out = validate_criterion({"ten": "X", "noi_dung_can_kiem_tra": [
        {"noi_dung_kiem_tra": "n1", "hsdt_kiem_tra": "don_du_thau", "ap_dung": "lien_danh"},
        {"noi_dung_kiem_tra": "n2", "hsdt_kiem_tra": "don_du_thau"}]})
    nds = out["noi_dung_can_kiem_tra"]
    assert nds[0]["ap_dung"] == "lien_danh" and nds[1]["ap_dung"] == ""   # mặc định rỗng


def test_sys_list_allows_cross_check_docs_in_hsdt_can_kiem_tra():
    """SYS_LIST phải cho phép khai THÊM tài liệu đối chiếu, nếu không luật liên-tài-liệu chết.

    Luật bang_gia_khop_webform khớp khi tiêu chí khai ĐỦ [bang_gia, webform]. Quy tắc nguyên tử
    cũ ("mỗi tiêu chí chỉ ... MỘT loại hồ sơ") ra lệnh model chỉ khai 1 mã -> luật không bao giờ
    bắn. Nguyên tử ràng buộc MỘT NỘI DUNG / MỘT HỒ SƠ CHÍNH, không cấm liệt kê tài liệu đối chiếu.
    """
    from experiment.decompose.prompts import SYS_LIST, list_prompt

    low = SYS_LIST.lower()
    assert "hồ sơ chính" in low and "đối chiếu" in low
    assert "một nội dung" in low                     # nguyên tử vẫn còn (ràng buộc nội dung)
    assert "webform" in list_prompt("nội dung nhóm")  # danh mục chào mã webform cho model


def test_sys_critique_atomic_rule_matches_sys_list():
    """Bước critique cũng sinh tiêu chí -> quy tắc nguyên tử phải NHẤT QUÁN với SYS_LIST.

    'mỗi tiêu chí = 1 loại hồ sơ + 1 nội dung' sẽ khiến tiêu chí do critique bổ sung chỉ khai 1 mã
    -> luật liên-tài-liệu không bắn cho đúng những tiêu chí bị sót.
    """
    from experiment.decompose.prompts import SYS_CRITIQUE

    low = SYS_CRITIQUE.lower()
    assert "hồ sơ chính" in low
    assert "1 loại hồ sơ + 1 nội dung" not in low     # câu cũ mâu thuẫn SYS_LIST


def test_sys_struct_picks_vendor_doc_not_reference_doc():
    """hsdt_kiem_tra phải là hồ sơ CỦA NHÀ THẦU bị chấm, không phải tài liệu đối chiếu.

    _skill_cho_nd khớp theo ho_so_can[0] == bang_gia; nếu model chọn webform thì luật không phục vụ.
    """
    from experiment.decompose.prompts import SYS_STRUCT

    low = SYS_STRUCT.lower()
    assert "bị chấm" in low or "của nhà thầu" in low
    assert "không phải tài liệu đối chiếu" in low


def test_sys_struct_forbids_inflating_yeu_cau():
    """SYS_STRUCT cấm yeu_cau đẻ điều kiện ngoài yeu_cau_goc — STRUCT không hề thấy HSMT.

    struct_prompt chỉ đưa tiêu chí (docstring: 'KHÔNG đưa source toàn nhóm') nên mọi điều kiện
    model thêm vào yeu_cau đều là bịa -> bước chấm gặp con trỏ ma -> 'cần làm rõ' giả.
    """
    from experiment.decompose.prompts import SYS_STRUCT

    low = SYS_STRUCT.lower()
    assert "không được thấy hsmt" in low or "không thấy hsmt" in low   # nêu rõ giới hạn suy diễn
    assert "không siết chặt hơn" in low
    assert "chính yeu_cau_goc" in low                                  # can_lam_ro bám gốc


def test_query_prompt_without_sources_unchanged():
    """Đơn nguồn: prompt KHÔNG nhắc gì tới nguồn — hành vi cũ giữ nguyên."""
    p = query_prompt({"ten": "Bảo đảm"}, {"noi_dung_kiem_tra": "Giá trị", "can_lam_ro": "Giá trị"})
    assert "nguon_goi_y" not in p
    assert "NGUỒN TÀI LIỆU" not in p


_GROUP = {
    "group": "hop_le",
    "muc": "Mục 1. Đánh giá tính hợp lệ",
    "is_reference": False,
    "ref_target": None,
    "blocks": [{"type": "text", "page": [27, 27],
                "text": "E-HSDT hợp lệ khi nộp trước thời điểm đóng thầu."}],
}
_SOURCES = {"hsmt": "Hồ sơ mời thầu chính: E-CDNT, E-BDL, biểu mẫu",
            "tbmt": "Thông báo mời thầu: thời gian phát hành/đóng/mở thầu, chủ đầu tư"}


def _nd(noi_dung, can_lam_ro=""):
    return {"noi_dung_kiem_tra": noi_dung, "hsdt_kiem_tra": "don_du_thau",
            "yeu_cau": "theo HSMT", "can_lam_ro": can_lam_ro, "can_tra_cuu": bool(can_lam_ro)}


def _crit(ten, contents):
    return {"nhom": "hop_le", "ten": ten, "yeu_cau_goc": f"{ten} theo HSMT",
            "hsdt_can_kiem_tra": ["don_du_thau"],
            "noi_dung_can_kiem_tra": contents}


def _nd_of(gd, ten, noi_dung):
    c = next(c for c in gd.criteria if c["ten"] == ten)
    return next(n for n in c["noi_dung_can_kiem_tra"] if n["noi_dung_kiem_tra"] == noi_dung)


def _llm_dong_thau(resolve_tag="[TAG:RESOLVE:Thời điểm đóng thầu]"):
    return ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Nộp thầu đúng hạn"}]},
        "[TAG:STRUCT:Nộp thầu đúng hạn]": _crit(
            "Nộp thầu đúng hạn", [_nd("Thời điểm đóng thầu", can_lam_ro="Thời điểm đóng thầu")]),
        "[TAG:QUERY:Thời điểm đóng thầu]": {"query": "thời điểm đóng thầu", "nguon_goi_y": ["tbmt"]},
        resolve_tag: {"thong_tin_bo_sung": "Đóng thầu: 09h00 ngày 20/6/2025",
                      "nguon": "", "can_review": False},
    })


async def test_search_routed_source_filters_and_attributes():
    """nguon_goi_y=['tbmt'] -> có lượt retrieve lọc source_doc='tbmt'; nguon backfill về TBMT."""
    captured: list[dict] = []

    def retrieve_fn(q, k=5, clause_doc=None, is_form=None, source_doc=None):
        captured.append({"q": q, "clause_doc": clause_doc, "source_doc": source_doc})
        if source_doc == "tbmt":
            return [{"text": "Thời điểm đóng thầu: 09 giờ 00 ngày 20/6/2025",
                     "metadata": {"chunk_id": "t1", "source_doc": "tbmt", "page_start": 1}, "score": 1.0}]
        return []

    wf = DecomposeWorkflow(llm_fn=_llm_dong_thau(), retrieve_fn=retrieve_fn, timeout=30,
                           source_summaries=_SOURCES)
    gd = await wf.run(group=_GROUP)

    nd = _nd_of(gd, "Nộp thầu đúng hạn", "Thời điểm đóng thầu")
    assert nd["thong_tin_bo_sung"] == "Đóng thầu: 09h00 ngày 20/6/2025"
    assert nd["nguon"] == "Thông báo mời thầu tr 1"          # nguon rỗng -> backfill theo source_doc
    assert any(c["source_doc"] == "tbmt" for c in captured)   # lượt tra ưu tiên nguồn gợi ý
    assert any(c["source_doc"] is None for c in captured)     # KÈM lượt không filter (route mềm)
    assert not any(c["clause_doc"] == "bdl" for c in captured)  # need đã route: không đi nhánh bdl
    assert gd.needs_review == []


async def test_search_wrapped_query_still_routes():
    """QUERY bị bọc trong 'result' -> vẫn route được nguồn (end-to-end vá vấn đề 1)."""
    captured: list[dict] = []

    def retrieve_fn(q, k=5, clause_doc=None, is_form=None, source_doc=None):
        captured.append({"q": q, "source_doc": source_doc})
        if source_doc == "tbmt":
            return [{"text": "Thời điểm đóng thầu: 09 giờ 00 ngày 20/6/2025",
                     "metadata": {"chunk_id": "t1", "source_doc": "tbmt", "page_start": 1}, "score": 1.0}]
        return []

    llm = _llm_dong_thau()
    llm.by_match["[TAG:QUERY:Thời điểm đóng thầu]"] = {
        "ly_do": "cần tra TBMT",
        "result": {"query": "thời điểm đóng thầu", "nguon_goi_y": ["tbmt"]},
    }
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30,
                           source_summaries=_SOURCES)
    gd = await wf.run(group=_GROUP)
    nd = _nd_of(gd, "Nộp thầu đúng hạn", "Thời điểm đóng thầu")
    assert nd["thong_tin_bo_sung"] and any(c["source_doc"] == "tbmt" for c in captured)


async def test_search_route_sai_van_duoc_retry_cuu():
    """Route sai (nguồn gợi ý không chứa thông tin) -> bậc retry KHÔNG filter vẫn cứu."""
    def retrieve_fn(q, k=5, clause_doc=None, is_form=None, source_doc=None):
        if source_doc is None and "chủ đầu tư" in q:  # chỉ query retry (góc khác, không filter) mới thấy
            return [{"text": "E-BDL 1.1 | Chủ đầu tư kiêm mốc đóng thầu: 09h00 20/6/2025",
                     "metadata": {"chunk_id": "x", "clause_id": "1.1", "clause_doc": "bdl"}, "score": 1.0}]
        return []

    llm = _llm_dong_thau(resolve_tag="[TAG:RESOLVE2:Thời điểm đóng thầu]")
    llm.by_match["[TAG:QUERY2:Thời điểm đóng thầu]"] = {"query": "chủ đầu tư thời gian nộp thầu"}
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=retrieve_fn, timeout=30,
                           source_summaries=_SOURCES)
    gd = await wf.run(group=_GROUP)

    nd = _nd_of(gd, "Nộp thầu đúng hạn", "Thời điểm đóng thầu")
    assert nd["can_review"] is False and "09h00" in nd["thong_tin_bo_sung"]
    assert gd.needs_review == []


async def test_search_scan_appendix_resolves_without_hits():
    """Nguồn scan NHỎ nạp NGUYÊN VĂN làm phụ lục -> resolve được dù retrieve trượt hoàn toàn."""
    llm = _llm_dong_thau()
    wf = DecomposeWorkflow(
        llm_fn=llm,
        retrieve_fn=lambda q, k=5, clause_doc=None, is_form=None, source_doc=None: [],
        timeout=30, source_summaries=_SOURCES,
        scan_texts={"tbmt": "THÔNG BÁO MỜI THẦU\nThời điểm đóng thầu: 09 giờ 00 ngày 20/6/2025"},
    )
    gd = await wf.run(group=_GROUP)

    nd = _nd_of(gd, "Nộp thầu đúng hạn", "Thời điểm đóng thầu")
    assert nd["can_review"] is False and "09h00" in nd["thong_tin_bo_sung"]
    resolves = [c for c in llm.calls if "[TAG:RESOLVE:" in c]
    assert resolves and "PHỤ LỤC — THÔNG BÁO MỜI THẦU" in resolves[0]
    assert "09 giờ 00" in resolves[0]           # nguyên văn TBMT có mặt trong bằng chứng
