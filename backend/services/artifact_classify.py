"""Kiểm tra file HSDT có khớp loại hồ sơ người dùng khai báo không."""
from __future__ import annotations
from typing import Any

from services import artifact_catalog
from services.ai_client import ai_call, settings
from services.prompts import cot_block
from services.ai_schemas import validate_validate_artifact

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
              + cot_block('{"match":true|false,"suggested_type":"<code hoặc rỗng>","confidence":0-1,"note":"..."}'))
    out = await ai_call(_SYS, prompt, mock_key="validate_artifact", validate=validate_validate_artifact)
    if out.status == "error":
        return {"match": False, "suggested_type": "", "confidence": 0.0,
                "note": f"AI lỗi khi kiểm tra loại hồ sơ: {out.error}", "_model": out.model}
    return {**out.data, "_model": out.model}
