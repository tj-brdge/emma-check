import pytest

from termscheck.plugins.muni.findings import build_finding


def built(dataset, prefix):
    d = next(x for x in dataset.defects if x.defect_id.startswith(prefix))
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    return d, h, build_finding(h.vendor_a, [h.position], d.true_terms, dataset.as_of)


def test_deferred_interest_finding(dataset):
    d, h, f = built(dataset, "D01")
    t = f.treatment
    assert f.income_impact_usd == pytest.approx(t.true_accrued * h.position.par / 100)
    assert t.true_accrued == pytest.approx(t.accreted_value - 100)
    assert "Income understated" in f.impact and "deferred-interest" in f.headline
    assert "zero coupon" in f.vendor_says and "11.000%" in f.document_says
    assert f.treatment.income_next_12m_vendor < 0 < f.treatment.income_next_12m_document


def test_cab_carried_as_current_pay_overstates_income(dataset):
    _, _, f = built(dataset, "D11")
    assert f.income_impact_usd < 0 and "Overbooked" in f.headline
    assert "should be reversed" in f.correct_treatment


def test_ccab_carried_as_zero_shows_run_rate_gap(dataset):
    _, _, f = built(dataset, "D12")
    assert abs(f.income_impact_usd) < 1
    assert f.run_rate_gap_usd > 50_000 and "run-rate" in f.headline


def test_correct_terms_produce_no_impact(dataset):
    _, _, f = built(dataset, "D04")
    assert abs(f.income_impact_usd) < 1 and abs(f.run_rate_gap_usd) < 1
    assert "no income impact" in f.headline.lower()


def test_rate_mismatch_headline(dataset):
    _, _, f = built(dataset, "D02")
    assert "coupon 1.000% vs document 5.750%" in f.headline and f.income_impact_usd > 0


def test_citations_flow_into_narrative_and_comparison(dataset):
    d = next(x for x in dataset.defects if x.defect_id.startswith("D01"))
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    cites = {"interest_type": {"page": 6, "excerpt": "x", "status": "verified"},
             "interest_rate_pct": {"page": 6, "excerpt": "y", "status": "verified"}}
    f = build_finding(h.vendor_a, [h.position], d.true_terms, dataset.as_of, citations=cites)
    assert "(p. 6)" in f.document_says
    row = next(r for r in f.comparison if r["field"] == "Interest type")
    assert row["vendor"] == "zero coupon" and row["document"] == "deferred_interest"
    assert row["match"] is False and row["page"] == 6


def test_impact_is_par_weighted_across_positions(dataset):
    from dataclasses import replace
    d = next(x for x in dataset.defects if x.defect_id.startswith("D01"))
    h = next(h for h in dataset.holdings if h.vendor_a.cusip == d.cusip)
    p2 = replace(h.position, portfolio="OTHER", par=1_000_000.0)
    f = build_finding(h.vendor_a, [h.position, p2], d.true_terms, dataset.as_of)
    per100 = f.treatment.unbooked_per_100
    assert f.income_impact_usd == pytest.approx(per100 * (h.position.par + 1_000_000) / 100)
