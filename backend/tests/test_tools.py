import json
from pathlib import Path

import pytest

from termscheck.extraction import RecordedExtractionClient
from termscheck.tools import compute_bond_treatment, extract_official_statement_terms

ROOT = Path(__file__).resolve().parents[2]


def test_tools_compose_end_to_end(dataset):
    d = next(x for x in dataset.defects if x.defect_id.startswith("D01"))
    rec = json.loads((Path(__file__).parent / "fixtures" / "recorded_extraction_D01.json").read_text())
    out = extract_official_statement_terms(str(ROOT / "data" / "sample_os" / f"OS_{d.cusip}.pdf"), d.cusip,
                                           llm=RecordedExtractionClient(rec))
    json.dumps(out)  # JSON-serialisable for MCP
    assert out["status"] == "ok" and out["interest_terms"]["interest_type"] == "deferred_interest"
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    t = compute_bond_treatment(out["interest_terms"], h.vendor_a.price, "clean", 0.0, "zero",
                               h.position.par, dataset.as_of.isoformat())
    json.dumps(t)
    assert t["unbooked_income_usd"] > 1_000_000
    assert t["yield_document_terms"] == pytest.approx(0.11, abs=0.002)
    assert t["schedule"][0]["value"] == pytest.approx(100.0)


def test_mbs_tool_from_plain_json():
    from termscheck.tools import compute_mbs_treatment
    terms = {"rate_type": "wac", "net_coupon": 0.0481, "payment_delay_days": 45, "issue_date": "2021-01-01",
             "maturity_date": "2051-01-01", "day_count": "30/360"}
    obs = [{"month": "2026-10-01", "factor": 0.86, "net_coupon": 0.04795},
           {"month": "2026-11-01", "factor": 0.85, "net_coupon": 0.04773}]
    out = compute_mbs_treatment(terms, {"cusip": "3137MBS09", "coupon": None, "factor": 0.85}, 1_000_000.0,
                                "2026-11-30", obs, [{"date": "2026-11-16", "cash": 3436.42, "type": "interest"}])
    json.dumps(out)
    # Oct 860,000 x 4.795%/12 = 3,436.4167 + Nov 850,000 x 4.773%/12 = 3,380.875
    assert out["unbooked_window_usd"] == pytest.approx(6_817.291667, abs=1e-4)
    assert out["book_rate"] is None and out["cash_implied_rate"] == pytest.approx(0.04795, abs=1e-6)
