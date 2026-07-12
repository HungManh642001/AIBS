"""Route theo nguồn tài liệu (step 3): schema + prompt + workflow."""
from experiment.decompose.prompts import query_prompt
from experiment.decompose.schema import validate_query


def test_validate_query_accepts_nguon_goi_y():
    out = validate_query({"query": "q", "nguon_goi_y": ["tbmt"]})
    assert out["nguon_goi_y"] == ["tbmt"]
    # thiếu field -> mặc định [] (script cũ chỉ trả {"query"} vẫn chạy)
    assert validate_query({"query": "q"})["nguon_goi_y"] == []


def test_query_prompt_with_sources_lists_catalog():
    p = query_prompt(
        {"ten": "Thời điểm đóng thầu"},
        {"noi_dung_kiem_tra": "Thời điểm đóng thầu", "can_lam_ro": "Thời điểm đóng thầu"},
        sources={"hsmt": "Hồ sơ mời thầu chính", "tbmt": "Thông báo mời thầu: thời gian phát hành/đóng/mở thầu"},
    )
    assert "[TAG:QUERY:Thời điểm đóng thầu]" in p          # tag giữ nguyên (ScriptedLlm khớp)
    assert "tbmt: Thông báo mời thầu" in p                  # danh mục nguồn có mặt
    assert "nguon_goi_y" in p                               # schema mở rộng


def test_query_prompt_without_sources_unchanged():
    """Đơn nguồn: prompt KHÔNG nhắc gì tới nguồn — hành vi cũ giữ nguyên."""
    p = query_prompt({"ten": "Bảo đảm"}, {"noi_dung_kiem_tra": "Giá trị", "can_lam_ro": "Giá trị"})
    assert "nguon_goi_y" not in p
    assert "NGUỒN TÀI LIỆU" not in p
