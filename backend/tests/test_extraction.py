"""Extraction tests against synthetic official statements (fictional issuers).

Offline tests use a recorded model response; the pipeline (page text, prompt, citation
verification, mapping to bond-math terms) runs for real. The live test calls the API.
"""
import copy
import json
import os
from pathlib import Path

import httpx2
import pytest

from termscheck.plugins.muni.bondmath import InterestType
from termscheck.extraction import (AnthropicExtractionClient, ExtractionLLMError, RecordedExtractionClient,
                                   extract_terms)
from termscheck.extraction.citations import normalise
from termscheck.extraction.pdf import extract_pages, select_pages
from termscheck.plugins.muni.extraction.schema import CITED_FIELDS, ExtractedTerms
from termscheck.extraction.sources import DocumentSource, UploadSource
from termscheck.plugins.muni.extraction.spec import MUNI_SPEC
from termscheck.plugins.muni.sources import EmmaSource

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures"


def defect(dataset, prefix):
    return next(d for d in dataset.defects if d.defect_id.startswith(prefix))


@pytest.fixture(scope="module")
def os_files(dataset):
    out = {}
    for p in ("D01", "D12"):
        d = defect(dataset, p)
        path = ROOT / "data" / "sample_os" / f"OS_{d.cusip}.pdf"
        assert path.exists(), "run scripts/make_sample_os.py"
        out[p] = (d, path.read_bytes(), json.loads((FIX / f"recorded_extraction_{p}.json").read_text()))
    return out


def run(os_files, p, recorded=None):
    d, pdf, rec = os_files[p]
    return extract_terms(pdf, d.cusip, RecordedExtractionClient(recorded or rec), MUNI_SPEC, model="test-model")


@pytest.mark.parametrize("p", ["D01", "D12"])
def test_every_extracted_field_has_verified_page_citation(os_files, p):
    r = run(os_files, p)
    assert r.status == "ok", r.problems
    filled = [c for c in r.checks if c.status != "absent"]
    assert {c.field for c in filled} >= {"interest_type", "interest_rate_pct", "compounding_frequency",
                                         "day_count", "accrual_start_date", "maturity_date"}
    for c in filled:
        assert c.page is not None and c.status == "verified", (c.field, c.status)
    for name in CITED_FIELDS:
        f = getattr(r.terms, name)
        if f.value is not None:
            assert f.page and f.excerpt, name
    assert r.terms.call_features and all(cf.page and cf.excerpt for cf in r.terms.call_features)


@pytest.mark.parametrize("p", ["D01", "D12"])
def test_extracted_terms_match_planted_ground_truth(os_files, p):
    d = os_files[p][0]
    t = run(os_files, p).interest_terms
    truth = d.true_terms
    for attr in ("interest_type", "rate", "dated_date", "maturity_date", "day_count",
                 "compounding_frequency", "conversion_date"):
        assert getattr(t, attr) == getattr(truth, attr), attr


def test_motivating_pattern_derived_from_document(os_files, dataset):
    """Zero vendor coupon + 'clean' price; the document says deferred interest at 11% paid at
    maturity. Nothing about the bond is hard-coded: terms come only from the PDF."""
    from termscheck.plugins.muni.findings import build_finding
    d = os_files["D01"][0]
    r = run(os_files, "D01")
    assert r.interest_terms.interest_type is InterestType.DEFERRED_INTEREST
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    f = build_finding(h.vendor_a, [h.position], r.interest_terms, dataset.as_of)
    assert h.vendor_a.coupon == 0 and h.vendor_a.price_convention == "clean"
    assert f.treatment.yield_document_terms == pytest.approx(0.11, abs=0.002)
    assert f.income_impact_usd > 1_000_000
    assert f.treatment.correct_clean == pytest.approx(100.0, abs=1.0)


def test_fabricated_excerpt_is_caught(os_files):
    rec = copy.deepcopy(os_files["D01"][2])
    rec["interest_rate_pct"]["excerpt"] = "The Deferred Interest Bonds will bear interest at 9.250% per annum."
    r = run(os_files, "D01", rec)
    c = r.checks_by_field()["interest_rate_pct"]
    assert c.status == "not_found" and r.status == "needs_review"


def test_wrong_page_is_reported(os_files):
    rec = copy.deepcopy(os_files["D01"][2])
    rec["day_count"]["page"] = 3
    c = run(os_files, "D01", rec).checks_by_field()["day_count"]
    assert c.status == "wrong_page" and c.found_on_page == 6


def test_value_must_carry_citation(os_files):
    rec = copy.deepcopy(os_files["D01"][2])
    rec["compounding_frequency"]["page"] = None
    r = run(os_files, "D01", rec)
    assert r.checks_by_field()["compounding_frequency"].status == "missing_citation"
    assert r.status == "needs_review"


def test_value_not_in_excerpt_is_reported(os_files):
    rec = copy.deepcopy(os_files["D01"][2])
    rec["interest_rate_pct"]["value"] = 12.0
    r = run(os_files, "D01", rec)
    assert r.checks_by_field()["interest_rate_pct"].value_in_excerpt is False
    assert r.status == "needs_review"


def test_missing_required_field_blocks_math(os_files):
    rec = copy.deepcopy(os_files["D01"][2])
    rec["interest_rate_pct"] = {"value": None, "page": None, "excerpt": None}
    r = run(os_files, "D01", rec)
    assert r.interest_terms is None and r.status == "needs_review"


def test_whitespace_and_hyphenation_tolerated():
    assert normalise("twelve\n30-day   months") == normalise("twelve 30-day months")
    assert normalise("accre-\nted value") == normalise("accreted value")


def test_prompt_contains_pages_and_target_but_no_vendor_data(os_files, dataset):
    d, pdf, rec = os_files["D01"]
    client = RecordedExtractionClient(rec)
    extract_terms(pdf, d.cusip, client, MUNI_SPEC, model="m")
    msg = client.calls[0]["user"]
    assert f"Target CUSIP: {d.cusip}" in msg and '<page number="6">' in msg
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    assert f"{h.vendor_a.price:.3f}" not in msg  # vendor data never sent: no anchoring


def test_page_prefilter_keeps_cusip_and_cover():
    pages = [f"filler page {i}" for i in range(1, 201)]
    pages[149] = "MATURITY SCHEDULE ... ABCDEFGH1 ..."
    pages[160] = "Interest will accrue and be compounded semiannually per annum"
    sel = select_pages(pages, "ABCDEFGH1", max_pages=5)
    assert 150 in sel.pages and 161 in sel.pages and 1 in sel.pages
    assert len(sel.pages) <= 5
    whole = select_pages(pages[:10], "X", max_pages=60)
    assert whole.pages == list(range(1, 11)) and not whole.truncated


def test_document_sources(tmp_path, os_files):
    store = UploadSource(tmp_path)
    assert isinstance(store, DocumentSource) and isinstance(EmmaSource(), DocumentSource)
    d, pdf, _ = os_files["D01"]
    ref = store.put(d.cusip, "os.pdf", pdf)
    assert store.list_documents(d.cusip) == [ref]
    assert store.fetch(ref).content == pdf
    with pytest.raises(ValueError):
        store.put(d.cusip, "x.pdf", b"not a pdf")
    with pytest.raises(NotImplementedError):
        EmmaSource().list_documents(d.cusip)


# ---------------------------------------------------------------- Anthropic client (SDK level, mocked HTTP)
def _mock_client(handler):
    import anthropic
    return anthropic.Anthropic(api_key="test", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def _message(text, stop_reason="end_turn"):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 500}}


def test_anthropic_client_structured_output_round_trip(os_files):
    d, pdf, rec = os_files["D01"]
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["beta"] = req.headers.get("anthropic-beta")
        return httpx2.Response(200, json=_message(json.dumps(rec)))

    llm = AnthropicExtractionClient(_mock_client(handler))
    r = extract_terms(pdf, d.cusip, llm, MUNI_SPEC, model="claude-sonnet-5-5")
    assert r.status == "ok" and r.model == "claude-sonnet-5-5"
    body = seen["body"]
    assert body["model"] == "claude-sonnet-5-5" and body["fallbacks"] == "default"
    assert "server-side-fallback" in seen["beta"]
    schema = body["output_config"]["format"]["schema"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False


def test_anthropic_client_refusal_and_truncation():
    for stop in ("refusal", "max_tokens"):
        llm = AnthropicExtractionClient(_mock_client(lambda req, s=stop: httpx2.Response(200, json=_message("{}", s))))
        with pytest.raises(ExtractionLLMError):
            llm.extract(system="s", user="u", model="claude-sonnet-5-5", max_tokens=10, schema=ExtractedTerms)


def test_default_model_is_configurable():
    from termscheck.settings import Settings
    assert Settings().extraction_model == "claude-sonnet-5-5"
    assert Settings(extraction_model="claude-opus-5-5").extraction_model == "claude-opus-5-5"


# ---------------------------------------------------------------- live
@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")
@pytest.mark.parametrize("p", ["D01", "D12"])
def test_live_extraction(os_files, p):
    from termscheck.settings import settings
    d, pdf, _ = os_files[p]
    r = extract_terms(pdf, d.cusip, AnthropicExtractionClient(), MUNI_SPEC, model=settings.extraction_model)
    for c in r.checks:
        if c.status != "absent":
            assert c.page is not None and c.ok, (c.field, c.status)
    t = r.interest_terms
    assert t is not None, r.problems
    for attr in ("interest_type", "rate", "dated_date", "maturity_date", "compounding_frequency",
                 "conversion_date"):
        assert getattr(t, attr) == getattr(d.true_terms, attr), attr
