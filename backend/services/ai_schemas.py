"""Pydantic schema validate output AI. Sai cấu trúc -> ném lỗi -> ai_call coi là error.

Chỉ còn schema của bước phân loại hồ sơ (services/artifact_classify). Các schema của pipeline bóc
tiêu chí cũ (criteria_list / criterion_detail / sub_check) đã bỏ cùng services/extraction.py; lõi
đánh giá mới tự validate trong experiment/evaluate/schema.py.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ValidateArtifactModel(_Base):
    match: bool
    suggested_type: str = ""
    confidence: float = 0.0
    note: str = ""


def validate_validate_artifact(d: dict[str, Any]) -> dict[str, Any]:
    return ValidateArtifactModel(**d).model_dump()
