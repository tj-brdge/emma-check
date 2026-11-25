from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from termscheck.settings import settings
from termscheck.api import audit, documents, findings, review, screens, uploads, workbench


def create_app() -> FastAPI:
    app = FastAPI(title="Terms Check", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
                       allow_methods=["*"], allow_headers=["*"])
    for r in (uploads.router, screens.router, documents.router, findings.router, review.router,
              workbench.router, audit.router):
        app.include_router(r)

    @app.exception_handler(Exception)
    async def unhandled(request, exc):
        """Always answer JSON, never leak internals: details go to the server log under an error id."""
        import logging
        import uuid

        from fastapi.responses import JSONResponse
        error_id = uuid.uuid4().hex[:12]
        logging.getLogger("termscheck").exception("unhandled error %s on %s %s", error_id, request.method,
                                                  request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": f"Internal error (id {error_id}). The details are in the server log.", "error_id": error_id})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
