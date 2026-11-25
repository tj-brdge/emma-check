"""Uploaded official statements, stored content-addressed (sha256) on local disk."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .base import DocumentRef, FetchedDocument


class UploadSource:
    name = "upload"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, cusip: str, filename: str, content: bytes) -> DocumentRef:
        if not content.startswith(b"%PDF"):
            raise ValueError("official statement must be a PDF")
        sha = hashlib.sha256(content).hexdigest()
        (self.root / f"{sha}.pdf").write_bytes(content)
        idx = self._index()
        idx.setdefault(cusip.upper(), {})[sha] = filename
        (self.root / "index.json").write_text(json.dumps(idx, indent=1))
        return DocumentRef("upload", sha, cusip.upper(), title=filename)

    def _index(self) -> dict:
        p = self.root / "index.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def list_documents(self, cusip: str) -> list[DocumentRef]:
        return [DocumentRef("upload", sha, cusip.upper(), title=fn)
                for sha, fn in self._index().get(cusip.upper(), {}).items()]

    def fetch(self, ref: DocumentRef) -> FetchedDocument:
        content = (self.root / f"{ref.ref}.pdf").read_bytes()
        return FetchedDocument(ref, ref.title or f"{ref.ref}.pdf", content,
                               hashlib.sha256(content).hexdigest())
