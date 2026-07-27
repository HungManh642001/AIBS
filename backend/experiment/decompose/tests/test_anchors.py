"""Bảng neo gói thầu: schema + prompt + build + workflow (hướng A — mốc chung tất định)."""
from experiment.decompose.anchors import build_anchors
from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.prompts import SYS_ANCHORS, anchors_prompt
from experiment.decompose.schema import validate_anchors
from experiment.decompose.workflow import DecomposeWorkflow


def test_validate_anchors_shape():
    out = validate_anchors({"neo": [{"ten": "thời điểm đóng thầu",
                                     "gia_tri": "09h00 ngày 20/6/2025", "nguon": "TBMT"}]})
    assert out["neo"][0]["ten"] == "thời điểm đóng thầu"
    assert validate_anchors({})["neo"] == []          # thiếu field -> mặc định rỗng


def test_anchors_prompt_catalog_and_tag():
    p = anchors_prompt("E-BDL 18.1 | Hiệu lực E-HSDT: 120 ngày\nTBMT: đóng thầu 09h00 20/6/2025")
    assert "[TAG:ANCHORS]" in p
    assert "thời điểm đóng thầu" in p and "thời điểm mở thầu" in p   # danh mục neo cố định
    assert "TBMT: đóng thầu" in p                                     # tư liệu có mặt
    assert "KHÔNG bịa" in SYS_ANCHORS


async def test_build_anchors_from_bdl_and_scans():
    llm = ScriptedLlm({"[TAG:ANCHORS]": {"neo": [
        {"ten": "thời điểm đóng thầu", "gia_tri": "09h00 ngày 20/6/2025", "nguon": "TBMT"},
        {"ten": "giá gói thầu", "gia_tri": "", "nguon": ""},      # rỗng -> loại (không bịa)
    ]}})
    out = await build_anchors(llm, [{"text": "E-BDL 18.1 | Hiệu lực: 120 ngày"}],
                              {"tbmt": "đóng thầu 09h00 20/6/2025"})
    assert out == {"thời điểm đóng thầu": {"gia_tri": "09h00 ngày 20/6/2025", "nguon": "TBMT"}}
    assert "E-BDL 18.1" in llm.calls[0] and "đóng thầu 09h00" in llm.calls[0]   # tư liệu đủ 2 nguồn


async def test_build_anchors_empty_or_error_returns_empty():
    assert await build_anchors(ScriptedLlm({}), [], {}) == {}          # không tư liệu -> không call
    llm = ScriptedLlm({})                                              # call nhưng không khớp -> error
    assert await build_anchors(llm, [{"text": "x"}], {}) == {}         # lỗi LLM -> {} (không bịa)
    assert llm.calls                                                   # đã thử call


_GROUP = {"group": "hop_le", "muc": "Mục 1", "is_reference": False, "ref_target": None,
          "blocks": [{"type": "text", "page": [1, 1],
                      "text": "Bảo lãnh dự thầu hiệu lực theo E-BDL."}]}


def _llm_hieu_luc():
    return ScriptedLlm({
        "[TAG:LIST]": {"criteria": [{"nhom": "hop_le", "ten": "Hiệu lực bảo lãnh"}]},
        "[TAG:STRUCT:Hiệu lực bảo lãnh]": {
            "nhom": "hop_le", "ten": "Hiệu lực bảo lãnh", "yeu_cau_goc": "Hiệu lực theo E-BDL",
            "hsdt_can_kiem_tra": ["bao_dam_du_thau"],
            "noi_dung_can_kiem_tra": [{
                "noi_dung_kiem_tra": "Thời hạn hiệu lực bảo lãnh", "hsdt_kiem_tra": "bao_dam_du_thau",
                "yeu_cau": "theo E-BDL", "can_lam_ro": "Thời hạn hiệu lực bảo lãnh", "can_tra_cuu": True}]},
        "[TAG:QUERY:Thời hạn hiệu lực bảo lãnh]": {"query": "hiệu lực bảo đảm dự thầu"},
        "[TAG:RESOLVE:Thời hạn hiệu lực bảo lãnh]": {
            "thong_tin_bo_sung": "≥ 120 ngày kể từ thời điểm đóng thầu (= 09h00 ngày 20/6/2025 [TBMT])",
            "nguon": "E-BDL 19.1", "can_review": False},
    })


def _retrieve_bdl(q, k=5, clause_doc=None, is_form=None, source_doc=None):
    return [{"text": "E-BDL 19.1 | Hiệu lực bảo đảm: ≥120 ngày kể từ thời điểm đóng thầu",
             "metadata": {"chunk_id": "b1", "clause_id": "19.1", "clause_doc": "bdl"}, "score": 1.0}]


async def test_resolve_prompt_carries_anchor_table():
    llm = _llm_hieu_luc()
    wf = DecomposeWorkflow(
        llm_fn=llm, retrieve_fn=_retrieve_bdl, timeout=30,
        anchors={"thời điểm đóng thầu": {"gia_tri": "09h00 ngày 20/6/2025", "nguon": "TBMT"}},
    )
    gd = await wf.run(group=_GROUP)
    resolves = [c for c in llm.calls if "[TAG:RESOLVE:" in c]
    assert resolves and "[BẢNG NEO — MỐC CHUNG GÓI THẦU]" in resolves[0]
    assert "- thời điểm đóng thầu: 09h00 ngày 20/6/2025 [TBMT]" in resolves[0]
    nd = gd.criteria[0]["noi_dung_can_kiem_tra"][0]
    assert "09h00 ngày 20/6/2025" in nd["thong_tin_bo_sung"]     # chuẩn đã TỰ ĐỦ


async def test_no_anchors_resolve_prompt_unchanged():
    llm = _llm_hieu_luc()
    wf = DecomposeWorkflow(llm_fn=llm, retrieve_fn=_retrieve_bdl, timeout=30)
    await wf.run(group=_GROUP)
    # neo theo nhãn khối ĐẦY ĐỦ: SYS_RESOLVE (nằm chung trong calls) cũng nhắc "BẢNG NEO"
    resolves = [c for c in llm.calls if "[TAG:RESOLVE:" in c]
    assert resolves and "[BẢNG NEO — MỐC CHUNG GÓI THẦU]" not in resolves[0]   # không neo -> y hệt cũ


def test_sys_resolve_teaches_anchor_substitution():
    from experiment.decompose.prompts import SYS_RESOLVE
    assert "BẢNG NEO" in SYS_RESOLVE and "GIỮ NGUYÊN" in SYS_RESOLVE
