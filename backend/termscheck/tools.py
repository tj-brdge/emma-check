"""Standalone, JSON-in/JSON-out facades over the extraction and bond-math modules.

These have no database or web dependencies, so they can be registered as MCP tools as-is
(e.g. with the MCP Python SDK: `mcp.tool()(extract_official_statement_terms)`).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from termscheck.core.plugin import get_plugin
from termscheck.plugins.muni.bondmath import VendorView, compute_treatment
from termscheck.services.serialize import jsonable


def extract_official_statement_terms(pdf_path: str, cusip: str, model: str = "claude-sonnet-5-5",
                                     llm: Any | None = None, asset_class: str = "muni") -> dict[str, Any]:
    """Extract interest terms for one CUSIP from an official statement PDF.

    Returns every field with value, page and verbatim excerpt, the deterministic citation
    check for each field, the mapped bond-math terms (or null) and an overall status.
    """
    from termscheck.extraction import AnthropicExtractionClient, extract_terms
    res = extract_terms(Path(pdf_path).read_bytes(), cusip, llm or AnthropicExtractionClient(),
                        get_plugin(asset_class).extraction, model=model)
    return {
        "cusip": res.cusip, "status": res.status, "model": res.model, "prompt_version": res.prompt_version,
        "fields": res.raw_json, "citation_checks": [c.as_dict() for c in res.checks],
        "interest_terms": jsonable(res.interest_terms) if res.interest_terms else None,
        "problems": res.problems, "pages_sent": res.selection.pages, "total_pages": res.selection.total_pages,
    }


def compute_bond_treatment(interest_terms: dict[str, Any], vendor_price: float, vendor_price_convention: str,
                           vendor_coupon: float, vendor_accrual_type: str, par: float, as_of: str,
                           acquisition_date: str | None = None) -> dict[str, Any]:
    """Correct accounting treatment for a position given document terms and vendor data.

    interest_terms: the `interest_terms` object returned by extract_official_statement_terms
    (rates as decimals, dates ISO). vendor_coupon is a decimal (0.05 = 5%). Prices per 100 par.
    """
    t = compute_treatment(
        get_plugin("muni").terms_from_json(interest_terms),
        VendorView(vendor_price, vendor_price_convention, vendor_coupon, vendor_accrual_type),
        par, date.fromisoformat(as_of),
        window_start=date.fromisoformat(acquisition_date) if acquisition_date else None)
    return jsonable(asdict(t))
