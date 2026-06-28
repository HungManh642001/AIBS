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

MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "eval_legality": {"result": "PASS", "score": 100, "evidence": "Đơn dự thầu có chữ ký hợp lệ", "page_ref": [1], "note": "Đầy đủ"},
    "eval_capacity": {"result": "PASS", "score": 85, "evidence": "Doanh thu 3 năm đạt 1.8 lần giá gói thầu", "page_ref": [4], "note": "Đạt yêu cầu"},
    "eval_technical": {"result": "PARTIAL", "score": 78, "evidence": "Đáp ứng 88% thông số kỹ thuật", "page_ref": [7], "note": "Thiếu 2 thông số phụ"},
    "eval_financial": {"result": "PASS", "score": 0, "evidence": "Bảng chào giá đầy đủ 12 hạng mục", "page_ref": [10], "note": "Cần hậu kiểm số học"},
    "extract_rubric": {
        "criteria": [
            {"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ", "yeu_cau": "Theo mẫu, có chữ ký",
             "required_artifacts": ["don_du_thau"], "kieu": "pass_fail", "trong_so": 0,
             "sub_checks": [
                 {"ten": "Có đơn dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "don_du_thau", "blocking": True},
                 {"ten": "Có chữ ký/đóng dấu", "check_type": "signature_stamp", "thong_so": {}, "required_artifact": "don_du_thau", "blocking": True},
             ], "proposed_artifacts": []},
            {"nhom": "hop_le", "ten": "Bảo đảm dự thầu", "yeu_cau": "Giá trị và hiệu lực theo HSMT",
             "required_artifacts": ["bao_dam_du_thau"], "kieu": "pass_fail", "trong_so": 0,
             "sub_checks": [
                 {"ten": "Có bảo đảm dự thầu", "check_type": "presence", "thong_so": {}, "required_artifact": "bao_dam_du_thau", "blocking": True},
                 {"ten": "Giá trị ≥ ngưỡng", "check_type": "value_threshold",
                  "thong_so": {"gia_tri_so": 150000000, "don_vi": "VND", "nguon": "BDS", "can_review": False},
                  "required_artifact": "bao_dam_du_thau", "blocking": True},
                 {"ten": "Hiệu lực ≥ yêu cầu", "check_type": "date_validity",
                  "thong_so": {"so_ngay": 120, "nguon": "BDS", "can_review": False},
                  "required_artifact": "bao_dam_du_thau", "blocking": True},
             ], "proposed_artifacts": []},
        ]
    },
    "validate_artifact": {"match": True, "suggested_type": "", "confidence": 1.0, "note": "Khớp loại khai báo"},
    "eval_subcheck": {"result": "PASS", "evidence": "Đáp ứng yêu cầu", "page_ref": [1]},
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
