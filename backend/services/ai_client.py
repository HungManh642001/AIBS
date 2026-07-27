"""Client gọi LiteLLM proxy -> Qwen3 27B, tự động fallback sang mock JSON."""
from __future__ import annotations
import copy
import logging
import os
from dataclasses import dataclass
from typing import Any, Callable

from services.json_utils import extract_json

# Dùng model cost map đóng gói sẵn, KHÔNG fetch từ internet (server on-premise).
# Phải đặt trước khi import litellm (litellm đọc biến này lúc import).
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from config import get_settings

logger = logging.getLogger("abes.ai")
settings = get_settings()

# Banner cho biết đang chạy chế độ AI nào (hiện ngay khi khởi động backend).
if settings.ai_mock:
    logger.warning("AI mode = MOCK (ABES_AI_MOCK=1) — KHÔNG gọi LLM thật.")
else:
    logger.warning(
        "AI mode = REAL — LiteLLM Proxy base=%s model=%s", settings.ai_base_url, settings.ai_model
    )

# Mock CHỈ phục vụ chạy demo không có proxy. Giữ đúng những key còn đường gọi thật — mock theo
# schema đã chết là bẫy bịa dữ liệu: bật ABES_AI_MOCK=1 sẽ trả payload mà không nơi nào hiểu.
MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "validate_artifact": {"match": True, "suggested_type": "", "confidence": 1.0, "note": "Khớp loại khai báo"},
}


def _litellm_completion(system: str, prompt: str, max_tokens: int | None = None) -> str:
    """Gọi LiteLLM Proxy (OpenAI-compatible /v1). Tách riêng để test dễ monkeypatch."""
    import litellm

    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"

    resp = litellm.completion(
        model=model,
        api_base=settings.ai_base_url,
        api_key=settings.ai_api_key or "sk-no-key",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=settings.ai_temperature,
        seed=settings.ai_seed,      # tái lập: xem chú thích ai_seed trong config
        top_p=1.0,
        max_tokens=max_tokens or settings.ai_max_tokens,
        timeout=300,
    )
    return resp["choices"][0]["message"]["content"]


@dataclass
class AiOutcome:
    """Kết quả 1 lượt gọi AI. status='error' nghĩa là KHÔNG có dữ liệu thật (không bịa mock)."""
    status: str            # "ok" | "error"
    data: dict[str, Any] | None
    model: str             # tên model thật | "mock"
    error: str | None = None


async def ai_call(
    system: str,
    prompt: str,
    *,
    mock_key: str,
    validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    max_tokens: int | None = None,
) -> AiOutcome:
    """Gọi AI và trả AiOutcome. Mock CHỈ khi ai_mock=1; chế độ thật lỗi -> status='error'."""
    if settings.ai_mock:
        if mock_key not in MOCK_RESPONSES:
            # no-silent-mock: không có mock hợp lệ thì báo lỗi, KHÔNG bịa payload sai schema.
            return AiOutcome(status="error", data=None, model="mock",
                             error=f"Chế độ mock không có dữ liệu cho '{mock_key}' — cần bật AI thật")
        data = copy.deepcopy(MOCK_RESPONSES[mock_key])
        if validate is not None:
            data = validate(data)
        return AiOutcome(status="ok", data=data, model="mock")

    last_err = ""
    for attempt in range(2):  # lần đầu + 1 retry
        try:
            raw = _litellm_completion(system, prompt, max_tokens=max_tokens)
            data = extract_json(raw)
            if validate is not None:
                data = validate(data)
            logger.info("AI[%s]: TRẢ KẾT QUẢ THẬT (model=%s).", mock_key, settings.ai_model)
            return AiOutcome(status="ok", data=data, model=settings.ai_model)
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            logger.warning("AI[%s]: lượt %d THẤT BẠI: %s", mock_key, attempt + 1, last_err)

    return AiOutcome(status="error", data=None, model=settings.ai_model, error=last_err)
