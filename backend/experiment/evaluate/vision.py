"""Render PDF scan -> ảnh, và cổng gọi Qwen VL (base64 inline, no internet).

Thật: default_vision_fn bọc litellm.completion với image_url data-URI. Test: ScriptedVision.
no-silent-mock: proxy lỗi -> AiOutcome(status='error'), KHÔNG bịa.
"""
from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable

import fitz  # PyMuPDF

from config import get_settings
from services.ai_client import AiOutcome  # read-only reuse
from services.json_utils import extract_json

VisionFn = Callable[..., Awaitable[AiOutcome]]


def page_to_png(page: fitz.Page, dpi: int = 200) -> bytes:
    """Một trang -> PNG bytes. Render theo TỪNG trang: trang đọc thẳng từ text nhúng khỏi render."""
    return page.get_pixmap(dpi=dpi).tobytes("png")


def pdf_to_images(data: bytes, dpi: int = 200) -> list[bytes]:
    """Mỗi trang PDF -> PNG bytes (để gửi model đọc ảnh)."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return [page_to_png(page, dpi=dpi) for page in doc]
    finally:
        doc.close()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _content(prompt: str, images: list[bytes]) -> Any:
    if not images:
        return prompt
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for png in images:
        parts.append({"type": "image_url", "image_url": {"url": _data_uri(png)}})
    return parts


async def default_vision_fn(
    system: str, prompt: str, images: list[bytes] = (), validate=None,
    max_tokens: int | None = None, seed: int | None = None,
) -> AiOutcome:
    """Gọi Qwen VL qua LiteLLM proxy (text + ảnh base64). Lỗi -> status='error'."""
    settings = get_settings()
    if settings.ai_mock:
        # Không có mock cho vision: nội dung phụ thuộc ảnh cụ thể, bịa ra là bịa bằng chứng.
        # Nhưng phải báo NGAY thay vì để người dùng chờ 2x300s timeout khi máy không có proxy.
        return AiOutcome(status="error", data=None, model="mock",
                         error="Chế độ mock không đọc được ảnh — cần bật AI thật để chấm HSDT")

    import litellm


    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"
    last_err = ""
    for _ in range(2):  # lần đầu + 1 retry
        try:
            resp = litellm.completion(
                model=model, api_base=settings.ai_base_url,
                api_key=settings.ai_api_key or "sk-no-key",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": _content(prompt, list(images))},
                ],
                temperature=settings.ai_temperature,
                seed=settings.ai_seed if seed is None else seed,   # xem chú thích ai_seed (config)
                top_p=1.0,
                max_tokens=max_tokens or settings.ai_max_tokens,
                timeout=300,
            )
            data = extract_json(resp["choices"][0]["message"]["content"])
            if validate is not None:
                data = validate(data)
            return AiOutcome(status="ok", data=data, model=settings.ai_model,
                             finish_reason=str(resp["choices"][0].get("finish_reason") or ""))
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
    return AiOutcome(status="error", data=None, model=settings.ai_model, error=last_err)


class ScriptedVision:
    """Vision kịch bản (test offline). by_match: substring-trong-(system+prompt) -> dict|Exception."""

    def __init__(self, by_match: dict[str, Any]):
        self.by_match = dict(by_match)
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, system: str, prompt: str, images: list[bytes] = (),
                       validate=None, **_kw: Any) -> AiOutcome:
        hay = f"{system}\n{prompt}"
        self.calls.append((hay, len(list(images))))
        for key, data in self.by_match.items():
            if key in hay:
                if isinstance(data, Exception):
                    return AiOutcome("error", None, "scripted", error=str(data))
                if validate is not None and data is not None:
                    data = validate(data)
                return AiOutcome("ok", data, "scripted")
        return AiOutcome("error", None, "scripted", error="ScriptedVision không khớp kịch bản")
