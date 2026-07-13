"""Bảng neo gói thầu: schema + prompt + build + workflow (hướng A — mốc chung tất định)."""
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
