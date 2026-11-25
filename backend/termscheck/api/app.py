from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..settings import settings
from . import documents, findings, review, screens, uploads, workbench


def create_app() -> FastAPI:
    app = FastAPI(title="Terms Check", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                       allow_methods=["*"], allow_headers=["*"])
    for r in (uploads.router, screens.router, documents.router, findings.router, review.router,
              workbench.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
