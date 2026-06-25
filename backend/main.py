"""ABES demo — FastAPI app factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from responses import ok


def create_app() -> FastAPI:
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
    init_db()
    app.include_router(packages.router)
    app.include_router(documents_router.router)

    @app.get("/api/v1/health")
    async def health() -> dict:
        return ok({"status": "up"})

    return app


app = create_app()
