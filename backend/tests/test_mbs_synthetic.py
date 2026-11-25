import pytest

from termscheck.plugins.agency_mbs.synthetic import generate, to_screen_input
from termscheck.screens import run_screens

FP_SEVERITY = 40      # below this a flag is informational (e.g. a PO labelled non-paying)


def test_dataset_shape(mbs_dataset):
    ds = mbs_dataset
    assert 45 <= len(ds.holdings) <= 55
    assert len({h.position.cusip for h in ds.holdings}) == len(ds.holdings)
    assert len(ds.defects) >= 6 and len(ds.traps) >= 2
    assert not any(h.position.cusip.startswith("31350A") for h in ds.holdings)
    covered = {r for d in ds.defects for r in d.expected_rules}
    assert {"null_vs_zero", "frequency_contradiction", "cash_reconciliation", "factor_mismatch",
            "rate_vs_disclosure", "vendor_disagreement"} <= covered


def test_m01_mirrors_the_motivating_pattern_without_its_terms(mbs_dataset):
    d = next(x for x in mbs_dataset.defects if x.defect_id.startswith("M01"))
    h = next(x for x in mbs_dataset.holdings if x.position.cusip == d.cusip)
    assert h.terms.rate_type.value == "wac"
    assert h.book.coupon == 0.0 and h.book.payment_frequency == 12
    assert h.vendors["FactSet"].coupon is None and h.vendors["FactSet"].is_blank("coupon")
    rates = [o.net_coupon for o in h.observations]
    assert all(r != pytest.approx(0.04773) for r in rates)       # generated, not the real security's rate
    assert any(round(r * 1e5) % 10 for r in rates)                # non-round (third decimal in percent)
    interest = [e for e in h.ledger if e.kind == "interest"]
    assert len(interest) == 12 and len({e.entry_date.month for e in interest}) == 12


@pytest.mark.parametrize("seed", [31350, 1, 2, 3])
def test_planted_defects_caught_and_traps_quiet(seed):
    ds = generate(seed)
    res = run_screens(to_screen_input(ds))
    by = res.by_cusip()
    for d in ds.defects:
        assert set(d.expected_rules) <= {f.rule for f in by.get(d.cusip, [])}, d.defect_id
    fps = [f for f in res.flags if f.cusip not in ds.defect_cusips and f.severity >= FP_SEVERITY]
    assert not fps, [(f.rule, f.message) for f in fps]
    for c in ds.traps:
        assert all(f.severity < FP_SEVERITY for f in by.get(c, []))


def test_cash_reconciliation_is_top_priority_for_m01(mbs_dataset):
    res = run_screens(to_screen_input(mbs_dataset))
    d = next(x for x in mbs_dataset.defects if x.defect_id.startswith("M01"))
    flags = sorted(res.by_cusip()[d.cusip], key=lambda f: -f.priority)
    assert flags[0].rule == "cash_reconciliation" and flags[0].confidence == 0.95
    c = flags[0].computed
    h = next(x for x in mbs_dataset.holdings if x.position.cusip == d.cusip)
    assert c["booked_total"] == 0 and c["book_rate"] == 0.0
    disclosed = sum(o.net_coupon for o in h.observations[-14:-2]) / 12   # accrual months Nov-25..Oct-26
    assert c["implied_rate"] == pytest.approx(disclosed, abs=2e-5)     # cash alone recovers the true rate
