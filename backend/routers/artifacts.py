"""Router danh mục loại hồ sơ HSDT — nguồn sự thật duy nhất cho dropdown frontend."""
from __future__ import annotations

from fastapi import APIRouter

from responses import ok
from services import artifact_catalog

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


@router.get("/artifacts")
async def list_artifacts():
    """Trả toàn bộ danh mục loại hồ sơ (code=value) để frontend hiển thị đồng bộ với backend."""
    return ok([
        {"value": code, "label": a["label"], "nhom": a["nhom"], "mo_ta": a["mo_ta"]}
        for code, a in artifact_catalog.CATALOG.items()
    ])
