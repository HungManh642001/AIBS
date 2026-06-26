"""Kiểm tra file HSDT có khớp loại hồ sơ người dùng khai báo không."""
from __future__ import annotations
from typing import Any

from services import artifact_catalog
from services.ai_client import ai_json, settings

_SYS = "Bạn là trợ lý phân loại hồ sơ thầu. Chỉ trả JSON."


def _text(pages: list[dict[str, Any]], limit: int = 6000) -> str:
    return "\n".join(p["text"] for p in pages)[:limit]


async def validate_artifact(file_pages: list[dict[str, Any]], declared_type: str) -> dict[str, Any]:
    text = _text(file_pages)
    if settings.ai_mock:
        # Mock tất định: dùng alias-matching thực tế của catalog
        code, conf = artifact_catalog.match_artifact(text)
        match = code is not None and code == declared_type
        return {"match": match, "suggested_type": code or "", "confidence": round(conf, 2),
                "note": "Khớp" if match else "Nội dung có thể không khớp loại khai báo", "_model": "mock"}
    declared = artifact_catalog.get_artifact(declared_type)
    label = declared["label"] if declared else declared_type
    prompt = (f"Loại khai báo: {label}. Nội dung file:\n{text}\n\n"
              'Trả JSON: {"match":true|false,"suggested_type":"<code hoặc rỗng>","confidence":0-1,"note":"..."}')
    return await ai_json(_SYS, prompt, mock_key="validate_artifact")
