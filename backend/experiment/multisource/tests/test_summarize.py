from experiment.decompose.llm import ScriptedLlm
from experiment.multisource.summarize import summarize_source


async def test_summarize_source_returns_tom_tat():
    llm = ScriptedLlm({"[TAG:SUMMARY:tbmt]":
                       {"tom_tat": "Thông báo mời thầu: thời gian phát hành/đóng/mở thầu, chủ đầu tư"}})
    s = await summarize_source("tbmt", [{"text": "THÔNG BÁO MỜI THẦU..."}], llm_fn=llm)
    assert "thời gian" in s
    # nội dung tài liệu phải nằm trong prompt (LLM đọc thật, không đoán từ mã nguồn)
    assert any("THÔNG BÁO MỜI THẦU..." in c for c in llm.calls)


async def test_summarize_source_error_falls_back_to_code():
    """LLM lỗi -> fallback = mã nguồn (route vẫn chạy được, KHÔNG bịa nội dung tóm tắt)."""
    llm = ScriptedLlm({"[TAG:SUMMARY:tbmt]": RuntimeError("proxy down")})
    assert await summarize_source("tbmt", [{"text": "x"}], llm_fn=llm) == "tbmt"
