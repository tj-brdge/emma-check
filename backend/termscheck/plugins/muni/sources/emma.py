"""EMMA (MSRB Electronic Municipal Market Access) source - interface placeholder only.

Intended behaviour when implemented: list_documents(cusip) returns the official statement
and relevant continuing-disclosure documents for the CUSIP's issue; fetch(ref) downloads the
PDF. It must respect MSRB terms of use and rate limits. Not implemented in v1 by design.
"""
from __future__ import annotations

from termscheck.extraction.sources.base import DocumentRef, FetchedDocument


class EmmaSource:
    name = "emma"

    def list_documents(self, cusip: str) -> list[DocumentRef]:
        raise NotImplementedError("EMMA retrieval is not implemented in v1; upload the official statement")

    def fetch(self, ref: DocumentRef) -> FetchedDocument:
        raise NotImplementedError("EMMA retrieval is not implemented in v1; upload the official statement")
