"""Shared document sources. Asset-class-specific sources (e.g. EMMA) live in their plugin."""
from termscheck.extraction.sources.base import DocumentRef, DocumentSource, FetchedDocument
from termscheck.extraction.sources.upload import UploadSource

__all__ = ["DocumentRef", "DocumentSource", "FetchedDocument", "UploadSource"]
