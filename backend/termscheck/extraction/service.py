"""Shared extraction pipeline: document text -> LLM structured output (plugin schema) ->
deterministic citation checks -> plugin term mapping. No database access."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from termscheck.extraction.citations import CitationCheck, check_excerpt
from termscheck.extraction.llm import ExtractionLLM
from termscheck.extraction.pdf import PageSelection, extract_pages, page_tagged_text, select_pages
from termscheck.extraction.spec import ExtractionSpec


@dataclass
class ExtractionResult:
    cusip: str
    plugin: str
    model: str
    prompt_version: str
    terms: BaseModel
    checks: list[CitationCheck]
    selection: PageSelection
    interest_terms: Any | None          # plugin-specific mapped terms (None if unusable)
    status: str                         # ok | needs_review
    problems: list[str] = field(default_factory=list)
    llm_meta: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def checks_by_field(self) -> dict[str, CitationCheck]:
        return {c.field: c for c in self.checks}


def _scalar(v: Any) -> Any:
    return v.value if hasattr(v, "value") and not isinstance(v, (str, int, float)) else v


def verify_citations(spec: ExtractionSpec, terms: BaseModel, pages: list[str]) -> list[CitationCheck]:
    checks = []
    for name in spec.cited_fields:
        f = getattr(terms, name)
        v = _scalar(f.value)
        checks.append(check_excerpt(name, f.page, f.excerpt, v is not None, pages, spec.value_repr(name, v)))
    for lf in spec.list_fields:
        for i, item in enumerate(getattr(terms, lf)):
            checks.append(check_excerpt(f"{lf}[{i}]", item.page, item.excerpt, True, pages))
    return checks


def extract_terms_from_pages(pages: list[str], cusip: str, llm: ExtractionLLM, spec: ExtractionSpec, *,
                             model: str, max_tokens: int = 16000, max_pages: int = 60) -> ExtractionResult:
    cusip = cusip.upper()
    sel = select_pages(pages, cusip, max_pages, spec.keywords or None)
    msg = spec.user_message(cusip, page_tagged_text(pages, sel.pages), sel.total_pages, sel.pages)
    resp = llm.extract(system=spec.system_prompt, user=msg, model=model, max_tokens=max_tokens,
                       schema=spec.schema)
    checks = verify_citations(spec, resp.terms, pages)
    mapped, problems = spec.map_terms(resp.terms)
    for c in checks:
        if not c.ok:
            where = f" (found on page {c.found_on_page})" if c.found_on_page else ""
            problems.append(f"{c.field}: citation {c.status}{where}")
        elif c.value_in_excerpt is False:
            problems.append(f"{c.field}: value not visible in its excerpt")
    if spec.identification_field:
        ex = getattr(resp.terms, spec.identification_field).excerpt or ""
        if cusip not in ex.upper().replace(" ", ""):
            problems.append(f"{spec.identification_field} excerpt does not contain the target CUSIP")
    if sel.truncated:
        problems.append(f"document prefiltered to {len(sel.pages)} of {sel.total_pages} pages")
    hard = [p for p in problems if not any(m in p for m in spec.soft_problem_markers)]
    status = "ok" if mapped is not None and not hard else "needs_review"
    return ExtractionResult(cusip, spec.key, resp.model, spec.prompt_version, resp.terms, checks, sel, mapped,
                            status, problems, resp.meta, resp.raw_json)


def extract_terms(pdf_bytes: bytes, cusip: str, llm: ExtractionLLM, spec: ExtractionSpec, *,
                  model: str, max_tokens: int = 16000, max_pages: int = 60) -> ExtractionResult:
    return extract_terms_from_pages(extract_pages(pdf_bytes), cusip, llm, spec, model=model,
                                    max_tokens=max_tokens, max_pages=max_pages)
