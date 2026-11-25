from __future__ import annotations

from fastapi import Header, HTTPException

from termscheck.db.session import get_session  # noqa: F401  (re-export for routers)


def current_user(x_user: str | None = Header(default=None)) -> str:
    """Prototype identity: the UI sends the reviewer's name in X-User. No authentication."""
    if not x_user or not x_user.strip():
        raise HTTPException(status_code=401, detail="X-User header required")
    return x_user.strip()[:128]


def get_store():
    from termscheck.extraction.sources import UploadSource
    from termscheck.settings import settings
    return UploadSource(settings.storage_dir)


class _RecordedByCusip:
    """Demo mode: serve recorded extractions from settings.recorded_dir/<CUSIP>.json."""

    def extract(self, *, system: str, user: str, model: str, max_tokens: int, schema):
        import json
        import re
        from pathlib import Path

        from termscheck.extraction.llm import ExtractionLLMError, RecordedExtractionClient
        from termscheck.settings import settings
        m = re.search(r"Target CUSIP: (\w{9})", user)
        p = Path(settings.recorded_dir) / f"{m.group(1) if m else ''}.json"
        if not p.exists():
            raise ExtractionLLMError(f"no recorded extraction for this CUSIP (demo mode); expected {p.name}")
        return RecordedExtractionClient(json.loads(p.read_text()), model="recorded").extract(
            system=system, user=user, model=model, max_tokens=max_tokens, schema=schema)


def get_llm():
    from termscheck.settings import settings
    if settings.llm_mode == "recorded":
        return _RecordedByCusip()
    from termscheck.extraction.llm import AnthropicExtractionClient
    return AnthropicExtractionClient(server_fallback=settings.extraction_server_fallback)
