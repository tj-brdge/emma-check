from dataclasses import replace
from datetime import date

import pytest

from termscheck.screens import (Position, PricePoint, ScreenConfig, ScreenInput, SecurityRecord,
                                run_screens)
from termscheck.plugins.muni.screens.peer_outlier import median_polish
from termscheck.plugins.muni.screens.price_drift import linear_fit
from termscheck.plugins.muni.synthetic import generate, to_screen_input

AS_OF = date(2026, 11, 30)
ALL_RULES = {"yield_coupon_impossibility", "price_drift", "peer_outlier", "vendor_disagreement",
             "zero_coupon_sanity"}


# ---------------------------------------------------------------- synthetic dataset
def test_dataset_shape(dataset):
    assert 195 <= len(dataset.holdings) <= 205
    assert len({h.vendor_a.cusip for h in dataset.holdings}) == len(dataset.holdings)
    assert len(dataset.defects) >= 10
    covered = {r for d in dataset.defects for r in d.expected_rules}
    assert covered == ALL_RULES, "every screen must have at least one planted defect"
    assert not any(h.vendor_a.cusip.startswith("34077") for h in dataset.holdings)


def test_generator_is_deterministic():
    a, b = generate(), generate()
    assert [h.vendor_a for h in a.holdings] == [h.vendor_a for h in b.holdings]


def test_planted_defects_are_caught(dataset, screen_result):
    by = screen_result.by_cusip()
    for d in dataset.defects:
        rules = {f.rule for f in by.get(d.cusip, [])}
        missing = set(d.expected_rules) - rules
        assert not missing, f"{d.defect_id} not caught by {missing}"


def test_motivating_pattern_flagged_on_three_screens(dataset, screen_result):
    d01 = next(d for d in dataset.defects if d.defect_id.startswith("D01"))
    rules = {f.rule for f in screen_result.by_cusip()[d01.cusip]}
    assert {"yield_coupon_impossibility", "zero_coupon_sanity", "price_drift"} <= rules


def test_false_positives_are_rare(dataset, screen_result):
    fps = [f for f in screen_result.flags if f.cusip not in dataset.defect_cusips]
    assert len(fps) <= 2, [(f.rule, f.message) for f in fps]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_screens_robust_across_seeds(seed):
    ds = generate(seed)
    res = run_screens(to_screen_input(ds))
    by = res.by_cusip()
    for d in ds.defects:
        assert set(d.expected_rules) <= {f.rule for f in by.get(d.cusip, [])}, d.defect_id
    fps = [f for f in res.flags if f.cusip not in ds.defect_cusips]
    assert len(fps) <= 3


def test_every_flag_is_fully_recorded(screen_result):
    assert screen_result.flags
    for f in screen_result.flags:
        assert f.rule in ALL_RULES
        assert 0 <= f.severity <= 100
        assert f.inputs and f.computed and f.message
    pri = [f.priority for f in screen_result.flags]
    assert pri == sorted(pri, reverse=True)          # ordered by severity x confidence
    assert all(0 < f.confidence <= 1 for f in screen_result.flags)
    assert screen_result.config["version"]


# ---------------------------------------------------------------- unit cases
def rec(**kw) -> SecurityRecord:
    base = dict(vendor="A", cusip="TEST00001", description="t", price=100.0, price_convention="clean",
                coupon=0.05, accrual_type="fixed", maturity_date=date(2036, 6, 1),
                issue_date=date(2016, 6, 1), rating="AA", sector="General Obligation", state="NY",
                payment_frequency=2, day_count="30/360", vendor_yield=None)
    base.update(kw)
    return SecurityRecord(**base)


def run_one(*records, secondary=(), history=None, config=None):
    data = ScreenInput(AS_OF, [Position("P", r.cusip, 1e6) for r in records],
                       {r.cusip: r for r in records}, {r.cusip: r for r in secondary}, history or {})
    return run_screens(data, config)


def test_yield_coupon_flags_zero_coupon_reporting_high_yield():
    r = rec(coupon=0.0, accrual_type="zero", price=150.0, vendor_yield=0.11)
    flags = [f for f in run_one(r).flags if f.rule == "yield_coupon_impossibility"]
    assert len(flags) == 1 and flags[0].computed["implied_yield"] < 0


def test_yield_coupon_quiet_when_consistent():
    r = rec(price=100.0, vendor_yield=0.05)   # par bond on... near a coupon date
    assert not [f for f in run_one(r).flags if f.rule == "yield_coupon_impossibility"]


def test_zero_coupon_sanity_thresholds():
    legit = rec(cusip="Z1", coupon=0.0, accrual_type="zero", price=62.0)
    near_par = rec(cusip="Z2", coupon=0.0, accrual_type="zero", price=101.0)
    short = rec(cusip="Z3", coupon=0.0, accrual_type="zero", price=99.0, maturity_date=date(2028, 6, 1))
    rules = {(f.cusip, f.rule) for f in run_one(legit, near_par, short).flags}
    assert ("Z2", "zero_coupon_sanity") in rules
    assert ("Z1", "zero_coupon_sanity") not in rules
    assert ("Z3", "zero_coupon_sanity") not in rules


def test_vendor_disagreement_normalises_labels_and_reports_fields():
    a = rec()
    same = replace(a, vendor="B", accrual_type="FIXED", price_convention="Clean")
    assert not run_one(a, secondary=[same]).flags
    diff = replace(a, vendor="B", coupon=0.0, payment_frequency=1, price_convention="dirty")
    flags = [f for f in run_one(a, secondary=[diff]).flags if f.rule == "vendor_disagreement"]
    assert set(flags[0].computed["differences"]) == {"coupon", "payment_frequency", "price_convention"}


def test_price_drift_detects_embedded_accrual_and_ignores_flat():
    months = [date(2026, m, 28) for m in range(1, 12)] + [AS_OF]
    acc = rec(cusip="DRIFT", coupon=0.0, accrual_type="zero", price=90.0, maturity_date=date(2033, 6, 1))
    flat = rec(cusip="FLAT", coupon=0.0, accrual_type="zero", price=70.0, maturity_date=date(2033, 6, 1))
    hist = {
        "DRIFT": [PricePoint("DRIFT", d, 82.0 + 0.7 * i) for i, d in enumerate(months)],  # +8.4/yr
        "FLAT": [PricePoint("FLAT", d, 70.0 - 0.2 + 0.0 * i) for i, d in enumerate(months)],
    }
    flags = {f.cusip for f in run_one(acc, flat, history=hist).flags if f.rule == "price_drift"}
    assert flags == {"DRIFT"}


def test_linear_fit_exact():
    a, b, r2 = linear_fit([0, 1, 2, 3], [1, 3, 5, 7])
    assert (a, b) == pytest.approx((1, 2)) and r2 == pytest.approx(1.0)


def test_median_polish_recovers_additive_effects():
    rows = []
    for band, be in (("a", 0.0), ("b", 0.01)):
        for rt, re_ in (("AA", 0.0), ("BBB", 0.005)):
            for sec, se in (("x", 0.0), ("y", 0.002)):
                for _ in range(3):
                    rows.append((0.03 + be + re_ + se, (band, rt, sec)))
    level, eff = median_polish(rows, min_n=3)
    fit = lambda k: level + sum(eff[i].get(k[i], 0) for i in range(3))  # noqa: E731
    assert all(fit(k) == pytest.approx(y, abs=1e-9) for y, k in rows)


def test_peer_threshold_is_configurable(dataset):
    data = to_screen_input(dataset)
    loose = run_screens(data, ScreenConfig(peer_z_threshold=2.0))
    strict = run_screens(data, ScreenConfig(peer_z_threshold=6.0))
    n = lambda r: sum(f.rule == "peer_outlier" for f in r.flags)  # noqa: E731
    assert n(loose) > n(strict)
    assert loose.config["peer_z_threshold"] == 2.0
