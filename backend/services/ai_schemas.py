"""Pydantic schema validate output AI. Sai cấu trúc -> ném lỗi -> ai_call coi là error."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EvalVerdictModel(_Base):
    evidence: str
    result: str
    score: float = 0.0
    page_ref: list[Any] = []
    note: str = ""


class SubVerdictModel(_Base):
    evidence: str
    result: str
    page_ref: list[Any] = []


class ValidateArtifactModel(_Base):
    match: bool
    suggested_type: str = ""
    confidence: float = 0.0
    note: str = ""


class CriterionListItem(_Base):
    nhom: str = "hop_le"
    ten: str
    required_artifacts: list[Any] = []


class CriteriaListModel(_Base):
    criteria: list[CriterionListItem]


class SubCheckModel(_Base):
    ten: str
    check_type: str = ""
    thong_so: dict[str, Any] = {}
    required_artifact: str = ""
    blocking: bool = True


class CriterionDetailModel(_Base):
    nhom: str = "hop_le"
    ten: str
    yeu_cau: str = ""
    required_artifacts: list[Any] = []
    kieu: str = "pass_fail"
    trong_so: float = 0.0
    sub_checks: list[SubCheckModel] = []
    proposed_artifacts: list[Any] = []


def validate_eval_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return EvalVerdictModel(**d).model_dump()


def validate_sub_verdict(d: dict[str, Any]) -> dict[str, Any]:
    return SubVerdictModel(**d).model_dump()


def validate_validate_artifact(d: dict[str, Any]) -> dict[str, Any]:
    return ValidateArtifactModel(**d).model_dump()


def validate_criteria_list(d: dict[str, Any]) -> dict[str, Any]:
    return CriteriaListModel(**d).model_dump()


def validate_criterion_detail(d: dict[str, Any]) -> dict[str, Any]:
    return CriterionDetailModel(**d).model_dump()
