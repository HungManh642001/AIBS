"""ABES demo — FastAPI app factory."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from responses import ok


def _setup_logging() -> None:
    """Hiện log tiến trình (INFO) của app+pipeline — mặc định Python chỉ hiện WARNING+."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for name in ("abes", "experiment"):
        lg = logging.getLogger(name)
        if not lg.handlers:
            lg.addHandler(handler)
        lg.setLevel(logging.INFO)
        lg.propagate = False  # tránh nhân đôi khi uvicorn cũng gắn handler ở root


def create_app() -> FastAPI:
    _setup_logging()
    app = FastAPI(title="ABES Demo", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from database import init_db
    from routers import packages
    from routers import documents as documents_router
    from routers import evaluation as evaluation_router
    from routers import reports as reports_router
    from routers import rubric as rubric_router
    init_db()
    app.include_router(packages.router)
    app.include_router(documents_router.router)
    app.include_router(evaluation_router.router)
    app.include_router(reports_router.router)
    app.include_router(rubric_router.router)

    @app.get("/api/v1/health")
    async def health() -> dict:
        from config import get_settings
        s = get_settings()
        return ok({"status": "up",
                   "ai_mode": "mock" if s.ai_mock else "real",
                   "ai_model": s.ai_model})

    return app


app = create_app()
