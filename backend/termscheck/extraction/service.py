"""Extraction pipeline: PDF bytes -> page text -> LLM structured output -> citation checks ->
bond-math terms. No database access; callable on its own (and as an MCP tool)."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..bondmath import DayCount, InterestTerms, InterestType
from .citations import CitationCheck, check_excerpt
from .llm import ExtractionLLM
from .pdf import PageSelection, extract_pages, page_tagged_text, select_pages
from .prompt import PROMPT_VERSION, SYSTEM, user_message
from .schema import CITED_FIELDS, ExtractedTerms

REQUIRED_FOR_MATH = ["interest_type", "interest_rate_pct", "accrual_start_date", "maturity_date"]


@dataclass
class ExtractionResult:
    cusip: str
    model: str
    prompt_version: str
    terms: ExtractedTerms
    checks: list[CitationCheck]
    selection: PageSelection
    interest_terms: InterestTerms | None
    status: str                        # ok | needs_review
    problems: list[str] = field(default_factory=list)
    llm_meta: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def checks_by_field(self) -> dict[str, CitationCheck]:
        return {c.field: c for c in self.checks}


def _value_repr(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    if name == "interest_rate_pct":
        return [f"{value:.3f}", f"{value:.2f}", f"{value:g}"]
    if name in ("accrual_start_date", "maturity_date", "first_payment_date", "first_compounding_date",
                "conversion_date"):
        try:
            d = date.fromisoformat(value)
        except ValueError:
            return None
        return [f"{calendar.month_name[d.month]} {d.day}, {d.year}", f"{d:%m/%d/%Y}", str(d.year)]
    return None


def verify_citations(terms: ExtractedTerms, pages: list[str]) -> list[CitationCheck]:
    checks = []
    for name in CITED_FIELDS:
        f = getattr(terms, name)
        v = f.value.value if hasattr(f.value, "value") else f.value
        checks.append(check_excerpt(name, f.page, f.excerpt, v is not None, pages, _value_repr(name, v)))
    for i, cf in enumerate(terms.call_features):
        checks.append(check_excerpt(f"call_features[{i}]", cf.page, cf.excerpt, True, pages))
    return checks


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def to_interest_terms(t: ExtractedTerms) -> tuple[InterestTerms | None, list[str]]:
    """Map extracted values to bond-math terms. Returns (terms or None, problems)."""
    problems: list[str] = []
    it = t.interest_type.value
    rate = t.interest_rate_pct.value
    start, mat = _date(t.accrual_start_date.value), _date(t.maturity_date.value)
    for name in REQUIRED_FOR_MATH:
        if getattr(t, name).value is None:
            problems.append(f"{name} not found in document")
    if t.accrual_start_date.value and start is None:
        problems.append("accrual_start_date is not a valid ISO date")
    if t.maturity_date.value and mat is None:
        problems.append("maturity_date is not a valid ISO date")
    if rate is not None and not (0 <= rate <= 30):
        problems.append(f"interest rate {rate}% outside plausible range")
    if problems:
        return None, problems
    itype = InterestType(it.value)
    comp = t.compounding_frequency.value
    if itype is not InterestType.CURRENT_PAY and comp is None:
        problems.append("compounding frequency not stated; assumed semiannual (muni convention)")
        comp = 2
    dc = DayCount(t.day_count.value.value) if t.day_count.value else DayCount.THIRTY_360
    if t.day_count.value is None:
        problems.append("day count not stated; muni default 30/360 applied")
    pay = t.payment_frequency.value or 2
    try:
        terms = InterestTerms(
            interest_type=itype, rate=rate / 100.0, dated_date=start, maturity_date=mat, day_count=dc,
            payment_frequency=pay if pay in (1, 2, 4, 12) else 2,
            compounding_frequency=comp if comp is not None else 2,
            first_coupon_date=_date(t.first_payment_date.value),
            first_compounding_date=_date(t.first_compounding_date.value),
            conversion_date=_date(t.conversion_date.value),
        )
    except ValueError as e:
        return None, problems + [f"terms inconsistent: {e}"]
    return terms, problems


def extract_terms_from_pages(pages: list[str], cusip: str, llm: ExtractionLLM, *, model: str,
                             max_tokens: int = 16000, max_pages: int = 60) -> ExtractionResult:
    cusip = cusip.upper()
    sel = select_pages(pages, cusip, max_pages)
    msg = user_message(cusip, page_tagged_text(pages, sel.pages), sel.total_pages, sel.pages)
    resp = llm.extract(system=SYSTEM, user=msg, model=model, max_tokens=max_tokens)
    checks = verify_citations(resp.terms, pages)
    terms, problems = to_interest_terms(resp.terms)
    for c in checks:
        if not c.ok:
            where = f" (found on page {c.found_on_page})" if c.found_on_page else ""
            problems.append(f"{c.field}: citation {c.status}{where}")
        elif c.value_in_excerpt is False:
            problems.append(f"{c.field}: value not visible in its excerpt")
    if cusip not in (resp.terms.security_identification.excerpt or "").upper().replace(" ", ""):
        problems.append("security_identification excerpt does not contain the target CUSIP")
    if sel.truncated:
        problems.append(f"document prefiltered to {len(sel.pages)} of {sel.total_pages} pages")
    hard = [p for p in problems if "assumed" not in p and "default" not in p
            and "prefiltered" not in p]
    status = "ok" if terms is not None and not hard else "needs_review"
    return ExtractionResult(cusip, resp.model, PROMPT_VERSION, resp.terms, checks, sel, terms,
                            status, problems, resp.meta, resp.raw_json)


def extract_terms(pdf_bytes: bytes, cusip: str, llm: ExtractionLLM, *, model: str,
                  max_tokens: int = 16000, max_pages: int = 60) -> ExtractionResult:
    return extract_terms_from_pages(extract_pages(pdf_bytes), cusip, llm, model=model,
                                    max_tokens=max_tokens, max_pages=max_pages)
