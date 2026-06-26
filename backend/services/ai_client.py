"""Client gọi LiteLLM proxy -> Qwen3 27B, tự động fallback sang mock JSON."""
from __future__ import annotations
import copy
import json
import logging
import os
from typing import Any

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
    "extract_criteria": {
        "criteria": [
            {"nhom": "hop_le", "ten": "Đơn dự thầu hợp lệ", "yeu_cau": "Mẫu đúng, có chữ ký", "kieu": "pass_fail", "trong_so": 0},
            {"nhom": "hop_le", "ten": "Bảo lãnh dự thầu", "yeu_cau": "Giá trị >= 3% giá gói thầu", "kieu": "pass_fail", "trong_so": 0},
            {"nhom": "nang_luc", "ten": "Doanh thu 3 năm", "yeu_cau": ">= 1.5 lần giá gói thầu", "kieu": "pass_fail", "trong_so": 0},
            {"nhom": "nang_luc", "ten": "Hợp đồng tương tự", "yeu_cau": ">= 1 hợp đồng tương tự", "kieu": "pass_fail", "trong_so": 0},
            {"nhom": "ky_thuat", "ten": "Đáp ứng thông số kỹ thuật", "yeu_cau": "Khớp >= 90% thông số", "kieu": "score", "trong_so": 60},
            {"nhom": "ky_thuat", "ten": "Tiến độ cung cấp", "yeu_cau": "<= 60 ngày", "kieu": "score", "trong_so": 40},
            {"nhom": "tai_chinh", "ten": "Giá dự thầu", "yeu_cau": "Bảng chào giá chi tiết", "kieu": "score", "trong_so": 0},
        ]
    },
    "map_hsdt": {"mappings": [{"criteria_ten": "Đơn dự thầu hợp lệ", "page_ref": [1], "content": "Đơn dự thầu ký ngày 01/06/2026"}]},
    "eval_legality": {"result": "PASS", "score": 100, "evidence": "Đơn dự thầu có chữ ký hợp lệ", "page_ref": [1], "note": "Đầy đủ"},
    "eval_capacity": {"result": "PASS", "score": 85, "evidence": "Doanh thu 3 năm đạt 1.8 lần giá gói thầu", "page_ref": [4], "note": "Đạt yêu cầu"},
    "eval_technical": {"result": "PARTIAL", "score": 78, "evidence": "Đáp ứng 88% thông số kỹ thuật", "page_ref": [7], "note": "Thiếu 2 thông số phụ"},
    "eval_financial": {"result": "PASS", "score": 0, "evidence": "Bảng chào giá đầy đủ 12 hạng mục", "page_ref": [10], "note": "Cần hậu kiểm số học"},
    "extract_de_cuong": {
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


def _litellm_completion(system: str, prompt: str) -> str:
    """Gọi LiteLLM Proxy (OpenAI-compatible /v1). Tách riêng để test dễ monkeypatch."""
    import litellm

    # LiteLLM Proxy expose endpoint OpenAI-compatible -> route qua provider "openai"
    # để litellm gọi đúng <api_base>/chat/completions với api_key.
    model = settings.ai_model
    if "/" not in model:
        model = f"openai/{model}"

    resp = litellm.completion(
        model=model,
        api_base=settings.ai_base_url,          # ví dụ: https://proxy.example.com/v1
        api_key=settings.ai_api_key or "sk-no-key",  # proxy không auth vẫn cần key khác rỗng
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        timeout=300,
    )
    return resp["choices"][0]["message"]["content"]


async def ai_json(system: str, prompt: str, *, mock_key: str) -> dict[str, Any]:
    if settings.ai_mock:
        logger.info("AI[%s]: dùng MOCK (ai_mock=1).", mock_key)
        return _mock(mock_key)
    try:
        logger.info("AI[%s]: gọi LiteLLM model=%s ...", mock_key, settings.ai_model)
        raw = _litellm_completion(system, prompt)
        data = json.loads(raw)
        data["_model"] = settings.ai_model
        logger.info("AI[%s]: LiteLLM TRẢ KẾT QUẢ THẬT (model=%s).", mock_key, settings.ai_model)
        return data
    except Exception as exc:
        logger.warning(
            "AI[%s]: gọi LiteLLM THẤT BẠI -> fallback MOCK. Lý do: %s: %s",
            mock_key, type(exc).__name__, exc,
        )
        return _mock(mock_key)


def _mock(mock_key: str) -> dict[str, Any]:
    data = copy.deepcopy(MOCK_RESPONSES[mock_key])
    data["_model"] = "mock"
    return data
