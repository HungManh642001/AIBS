"""Chuẩn hóa response envelope: {"success", "data", "error"}."""
from typing import Any
from fastapi.responses import JSONResponse


def ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def fail(error: str, code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"success": False, "data": None, "error": error},
    )
