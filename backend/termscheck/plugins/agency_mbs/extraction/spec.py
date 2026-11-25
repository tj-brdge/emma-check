"""Agency MBS extraction spec: schema, prompt and mapping to MBSTerms."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from termscheck.core.daycount import DayCount
from termscheck.extraction.spec import ExtractionSpec
from termscheck.plugins.agency_mbs.bondmath import MBSTerms, RateType
from termscheck.plugins.agency_mbs.extraction.prompt import PROMPT_VERSION, SYSTEM
from termscheck.plugins.agency_mbs.extraction.schema import CITED_FIELDS, MBSExtractedTerms

REQUIRED = ["rate_type", "payment_delay_days", "issue_date", "maturity_date"]
DATE_FIELDS = {"issue_date", "first_payment_date", "maturity_date", "factor_date"}
KEYWORDS = {r"pass-through rate": 5, r"net coupon": 5, r"weighted average coupon": 5, r"\bwac\b": 4,
            r"payment delay": 5, r"day delay": 4, r"30-day months": 4, r"360-day year": 4, r"pool factor": 4,
            r"interest rate": 2, r"guarantee fee": 3, r"servicing fee": 3, r"index": 2, r"margin": 2,
            r"cusip": 2, r"pool number": 3, r"first payment date": 3, r"maturity date": 3}


def value_repr(name: str, value: Any) -> list[str] | None:
    if value is None:
        return None
    if name in ("net_coupon_pct", "rate_spread_pct"):
        return [f"{value:.3f}", f"{value:.2f}", f"{value:g}"]
    if name == "payment_delay_days":
        return [str(value)]
    if name in DATE_FIELDS:
        try:
            d = date.fromisoformat(value)
        except ValueError:
            return None
        return [f"{calendar.month_name[d.month]} {d.day}, {d.year}", f"{calendar.month_name[d.month]} {d.year}",
                f"{d:%m/%d/%Y}", f"{d:%m/%Y}", str(d.year)]
    return None


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def to_mbs_terms(t: MBSExtractedTerms) -> tuple[dict | None, list[str]]:
    """Returns a JSON-able terms dict (MBSTerms fields + document extras), or None with problems."""
    problems = [f"{n} not found in document" for n in REQUIRED if getattr(t, n).value is None]
    rt = t.rate_type.value
    rate = t.net_coupon_pct.value
    if rt is not None and rt.value == "fixed" and rate is None:
        problems.append("fixed-rate security without a stated net coupon")
    if rate is not None and not 0 <= rate <= 20:
        problems.append(f"net coupon {rate}% outside plausible range")
    issue, mat = _date(t.issue_date.value), _date(t.maturity_date.value)
    if t.issue_date.value and issue is None:
        problems.append("issue_date is not a valid ISO date")
    if problems:
        return None, problems
    dc = t.day_count.value.value if t.day_count.value else None
    if dc is None:
        problems.append("day count not stated; 30/360 (agency MBS convention) applied")
    elif dc != "30/360":
        return None, problems + [f"day count {dc} stated; only 30/360 monthly accrual is implemented"]
    terms = {
        "rate_type": rt.value, "net_coupon": None if rate is None else rate / 100.0,
        "payment_delay_days": t.payment_delay_days.value, "issue_date": issue.replace(day=1).isoformat(),
        "maturity_date": mat.isoformat(), "day_count": "30/360",
        "reset_rule": t.reset_rule.value,
        "rate_spread": None if t.rate_spread_pct.value is None else t.rate_spread_pct.value / 100.0,
        "stated_factor": t.current_factor.value, "stated_factor_date": t.factor_date.value,
        "product_type": t.product_type.value.value if t.product_type.value else None,
        "first_payment_date": t.first_payment_date.value,
    }
    try:
        terms_from_json(terms)
    except ValueError as e:
        return None, problems + [f"terms inconsistent: {e}"]
    if rt.value != "fixed" and not t.reset_rule.value:
        problems.append("variable rate without a quoted reset rule")
    return terms, problems


def terms_from_json(d: dict, observations=()) -> MBSTerms:
    return MBSTerms(RateType(d["rate_type"]), d.get("net_coupon"), int(d["payment_delay_days"]),
                    date.fromisoformat(d["issue_date"]), date.fromisoformat(d["maturity_date"]),
                    DayCount(d.get("day_count") or "30/360"), d.get("reset_rule"), tuple(observations))


MBS_SPEC = ExtractionSpec(
    key="agency_mbs", document_label="offering circular supplement", schema=MBSExtractedTerms,
    system_prompt=SYSTEM, prompt_version=PROMPT_VERSION, cited_fields=tuple(CITED_FIELDS),
    identification_field="security_identification", keywords=KEYWORDS, value_repr=value_repr,
    map_terms=to_mbs_terms,
)
