"""Bảng neo gói thầu: schema + prompt + build + workflow (hướng A — mốc chung tất định)."""
from experiment.decompose.anchors import build_anchors
from experiment.decompose.llm import ScriptedLlm
from experiment.decompose.prompts import SYS_ANCHORS, anchors_prompt
from experiment.decompose.schema import validate_anchors


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
