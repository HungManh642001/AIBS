import pytest
from services import ai_schemas


def test_validate_artifact_ok():
    out = ai_schemas.validate_validate_artifact(
        {"match": True, "suggested_type": "don_du_thau", "confidence": 0.9, "note": "Khớp"})
    assert out["match"] is True and out["suggested_type"] == "don_du_thau"


def test_validate_artifact_chi_can_truong_match():
    """Các trường phụ thiếu -> lấy mặc định, không ném lỗi."""
    out = ai_schemas.validate_validate_artifact({"match": False})
    assert out["match"] is False and out["suggested_type"] == "" and out["confidence"] == 0.0


def test_validate_artifact_thieu_match_raises():
    """Thiếu trường bắt buộc -> ném lỗi -> ai_call coi là error (no-silent-mock)."""
    with pytest.raises(Exception):
        ai_schemas.validate_validate_artifact({"note": "thiếu match"})


def test_validate_artifact_bo_qua_truong_la():
    out = ai_schemas.validate_validate_artifact({"match": True, "thua": "bỏ qua"})
    assert "thua" not in out
