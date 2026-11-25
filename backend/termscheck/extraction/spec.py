"""What an asset-class plugin supplies to the shared extraction pipeline."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ExtractionSpec:
    key: str                                   # plugin key, e.g. "muni"
    document_label: str                        # e.g. "official statement"
    schema: type[BaseModel]                    # every field carries page + verbatim excerpt
    system_prompt: str
    prompt_version: str
    cited_fields: tuple[str, ...]              # scalar fields with value/page/excerpt
    list_fields: tuple[str, ...] = ()          # list fields whose items carry page/excerpt
    identification_field: str | None = None   # field whose excerpt must contain the CUSIP
    keywords: dict[str, int] = field(default_factory=dict)   # page prefilter weights
    value_repr: Callable[[str, Any], list[str] | None] = lambda name, v: None
    map_terms: Callable[[BaseModel], tuple[Any | None, list[str]]] = lambda t: (None, ["no mapping"])
    soft_problem_markers: tuple[str, ...] = ("assumed", "default", "prefiltered")

    def user_message(self, cusip: str, page_text: str, total_pages: int, sent_pages: list[int]) -> str:
        return (
            f"Target CUSIP: {cusip}\n"
            f"The document has {total_pages} pages; pages provided: {sent_pages}.\n\n"
            f"<document>\n{page_text}\n</document>\n\n"
            f"Extract the terms for CUSIP {cusip}."
        )
