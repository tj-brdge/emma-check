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
    async def unhandled(request, exc):   # always answer JSON, never a bare text 500
        import logging
        logging.getLogger("termscheck").exception("unhandled error on %s", request.url.path)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": f"internal error: {type(exc).__name__}: {exc}"})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
