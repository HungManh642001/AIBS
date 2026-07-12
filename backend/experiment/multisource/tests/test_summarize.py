from experiment.decompose.llm import ScriptedLlm
from experiment.multisource.summarize import summarize_source

_CARD = {"tom_tat": "Thông báo mời thầu: thông tin công bố gói thầu",
         "cac_truong": ["thời điểm đóng/mở thầu", "địa điểm", "chủ đầu tư"]}


async def test_summarize_from_page_gists_not_truncated_text():
    """Có gist -> thẻ nguồn build TỪ GIST từng trang (map-reduce), KHÔNG nạp text thô cắt 8k."""
    llm = ScriptedLlm({"[TAG:SUMMARY:tbmt]": _CARD})
    chunks = [
        {"text": "x" * 500, "page_gist": "thời điểm đóng/mở thầu"},
        {"text": "y" * 500, "page_gist": "thời điểm đóng/mở thầu"},   # gist trùng trang -> khử trùng
        {"text": "z" * 500, "page_gist": "địa điểm, chủ đầu tư"},
    ]
    card = await summarize_source("tbmt", chunks, llm_fn=llm)

    assert card["tom_tat"].startswith("Thông báo mời thầu")
    assert "địa điểm" in card["cac_truong"][1]
    prompt = next(c for c in llm.calls if "[TAG:SUMMARY:tbmt]" in c)
    assert "thời điểm đóng/mở thầu" in prompt and "địa điểm, chủ đầu tư" in prompt
    # gist trùng chỉ đưa 1 lần (đếm theo dòng gist "- ..."; SYS cũng nhắc cụm này trong ví dụ)
    assert prompt.count("- thời điểm đóng/mở thầu") == 1
    assert "xxxx" not in prompt                          # KHÔNG nạp text thô


async def test_summarize_falls_back_to_text_without_gists():
    """Chunk cũ không có gist -> fallback nạp text (cắt trần) như trước."""
    llm = ScriptedLlm({"[TAG:SUMMARY:tbmt]": _CARD})
    card = await summarize_source("tbmt", [{"text": "THÔNG BÁO MỜI THẦU..."}], llm_fn=llm)

    assert card["cac_truong"]
    assert any("THÔNG BÁO MỜI THẦU..." in c for c in llm.calls)


async def test_summarize_error_falls_back_to_code_card():
    """LLM lỗi -> thẻ fallback {tom_tat=mã nguồn, cac_truong=[]} (route vẫn chạy, KHÔNG bịa)."""
    llm = ScriptedLlm({"[TAG:SUMMARY:tbmt]": RuntimeError("proxy down")})
    assert await summarize_source("tbmt", [{"text": "x"}], llm_fn=llm) == {
        "tom_tat": "tbmt", "cac_truong": []}
