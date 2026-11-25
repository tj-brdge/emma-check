"""Shared document-term extraction pipeline. Asset-class plugins supply an ExtractionSpec."""
from termscheck.extraction.citations import CitationCheck
from termscheck.extraction.llm import AnthropicExtractionClient, ExtractionLLMError, RecordedExtractionClient
from termscheck.extraction.service import ExtractionResult, extract_terms, extract_terms_from_pages
from termscheck.extraction.spec import ExtractionSpec

__all__ = ["AnthropicExtractionClient", "CitationCheck", "ExtractionLLMError", "ExtractionResult",
           "ExtractionSpec", "RecordedExtractionClient", "extract_terms", "extract_terms_from_pages"]
