"""Client gọi LiteLLM proxy -> Qwen3 27B, tự động fallback sang mock JSON."""
from __future__ import annotations
import copy
import json
from typing import Any

from config import get_settings

settings = get_settings()

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
    """Tách riêng để test dễ monkeypatch. Trả về chuỗi JSON."""
    import litellm

    resp = litellm.completion(
        model=settings.ai_model,
        api_base=settings.ai_base_url,
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
        return _mock(mock_key)
    try:
        raw = _litellm_completion(system, prompt)
        data = json.loads(raw)
        data["_model"] = settings.ai_model
        return data
    except Exception:
        return _mock(mock_key)


def _mock(mock_key: str) -> dict[str, Any]:
    data = copy.deepcopy(MOCK_RESPONSES[mock_key])
    data["_model"] = "mock"
    return data
