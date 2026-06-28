"""Cổng gọi LLM cho workflow phân rã.

Thật: `default_llm_fn` bọc `services.ai_client.ai_call` (LiteLLM proxy, no-silent-mock + retry +
trích JSON + validate). Test: `ScriptedLlm` trả JSON kịch bản, khớp theo tag trong prompt.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from services.ai_client import AiOutcome, ai_call  # read-only reuse

# llm_fn(system, prompt, validate=None, max_tokens=None) -> AiOutcome
LlmFn = Callable[..., Awaitable[AiOutcome]]


async def default_llm_fn(
    system: str,
    prompt: str,
    validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    *,
    mock_key: str = "extract_rubric",
    max_tokens: int | None = None,
) -> AiOutcome:
    """Gọi LLM thật qua proxy. Proxy lỗi -> AiOutcome(status='error') (KHÔNG bịa)."""
    return await ai_call(system, prompt, mock_key=mock_key, validate=validate, max_tokens=max_tokens)


class ScriptedLlm:
    """LLM kịch bản (test offline). `by_match`: substring-trong-prompt -> dict|Exception.

    Khớp key ĐẦU TIÊN xuất hiện trong (system+prompt). Bền với fan-out chạy song song
    (khớp theo tag, không theo thứ tự gọi).
    """

    def __init__(self, by_match: dict[str, Any]):
        self.by_match = dict(by_match)
        self.calls: list[str] = []

    async def __call__(
        self,
        system: str,
        prompt: str,
        validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        **_kw: Any,
    ) -> AiOutcome:
        hay = f"{system}\n{prompt}"
        self.calls.append(hay)
        for key, data in self.by_match.items():
            if key in hay:
                if isinstance(data, Exception):
                    return AiOutcome("error", None, "scripted", error=str(data))
                if validate is not None and data is not None:
                    data = validate(data)
                return AiOutcome("ok", data, "scripted")
        return AiOutcome("error", None, "scripted", error="không khớp kịch bản ScriptedLlm")
