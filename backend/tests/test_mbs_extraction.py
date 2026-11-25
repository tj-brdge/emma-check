import copy
import json
from pathlib import Path

import pytest

from termscheck.extraction import RecordedExtractionClient, extract_terms
from termscheck.plugins.agency_mbs.extraction.spec import MBS_SPEC

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures"


def load(mbs_dataset, key):
    d = next(x for x in mbs_dataset.defects if x.defect_id.startswith(key))
    h = next(x for x in mbs_dataset.holdings if x.position.cusip == d.cusip)
    pdf = (ROOT / "data" / "sample_os" / f"SUPP_{d.cusip}.pdf").read_bytes()
    rec = json.loads((FIX / f"recorded_extraction_{key}.json").read_text())
    return h, pdf, rec


@pytest.mark.parametrize("key", ["M01", "M02"])
def test_every_field_cited_and_verified(mbs_dataset, key):
    h, pdf, rec = load(mbs_dataset, key)
    r = extract_terms(pdf, h.position.cusip, RecordedExtractionClient(rec), MBS_SPEC, model="m")
    assert r.status == "ok", r.problems
    filled = [c for c in r.checks if c.status != "absent"]
    assert {"rate_type", "payment_delay_days", "day_count", "issue_date", "maturity_date"} <= {c.field for c in filled}
    assert all(c.page and c.status == "verified" for c in filled)


@pytest.mark.parametrize("key", ["M01", "M02"])
def test_terms_match_generated_truth(mbs_dataset, key):
    h, pdf, rec = load(mbs_dataset, key)
    t = extract_terms(pdf, h.position.cusip, RecordedExtractionClient(rec), MBS_SPEC, model="m").interest_terms
    assert t["rate_type"] == h.terms.rate_type.value
    assert t["payment_delay_days"] == h.terms.payment_delay_days
    assert t["issue_date"] == h.terms.issue_date.isoformat() and t["maturity_date"] == h.terms.maturity_date.isoformat()
    if key == "M02":
        assert t["net_coupon"] == h.terms.net_coupon
    else:
        assert t["rate_spread"] == h.meta["fee"] and t["net_coupon"] == h.meta["initial_rate"]


def test_missing_delay_blocks_terms(mbs_dataset):
    h, pdf, rec = load(mbs_dataset, "M02")
    rec = copy.deepcopy(rec)
    rec["payment_delay_days"] = {"value": None, "page": None, "excerpt": None}
    r = extract_terms(pdf, h.position.cusip, RecordedExtractionClient(rec), MBS_SPEC, model="m")
    assert r.interest_terms is None and r.status == "needs_review"


def test_wrong_rate_type_excerpt_caught(mbs_dataset):
    h, pdf, rec = load(mbs_dataset, "M01")
    rec = copy.deepcopy(rec)
    rec["rate_type"] = {"value": "fixed", "page": 3, "excerpt": "The Certificates bear a fixed rate."}
    r = extract_terms(pdf, h.position.cusip, RecordedExtractionClient(rec), MBS_SPEC, model="m")
    assert r.checks_by_field()["rate_type"].status == "not_found" and r.status == "needs_review"
