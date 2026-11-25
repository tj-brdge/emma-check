"""Where official statements come from. v1: user upload. Later: EMMA retrieval.

A DocumentSource lists candidate documents for a CUSIP and fetches their bytes. Everything
downstream (page text, extraction, citation checks) works on FetchedDocument only, so adding
an EMMA source requires no change to extraction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class DocumentRef:
    source: str                 # "upload" | "emma" | ...
    ref: str                    # source-specific id (sha256 for uploads, EMMA doc id later)
    cusip: str
    title: str | None = None
    doc_type: str = "official_statement"
    posted_date: date | None = None
    url: str | None = None


@dataclass(frozen=True)
class FetchedDocument:
    ref: DocumentRef
    filename: str
    content: bytes
    sha256: str
    media_type: str = "application/pdf"
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class DocumentSource(Protocol):
    name: str

    def list_documents(self, cusip: str) -> list[DocumentRef]: ...

    def fetch(self, ref: DocumentRef) -> FetchedDocument: ...
