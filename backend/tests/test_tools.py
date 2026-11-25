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
