"""One screen run over both asset classes, through the HTTP API and PostgreSQL."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.db
SYN = Path(__file__).resolve().parents[2] / "data" / "synthetic"
OS = Path(__file__).resolve().parents[2] / "data" / "sample_os"


def up(client, kind, fn, vendor=None):
    r = client.post(f"/api/uploads/{kind}", files={"file": (fn, (SYN / fn).read_bytes(), "text/csv")},
                    data={"vendor": vendor} if vendor else {})
    assert r.status_code == 200, r.text
    return r.json()["batch"]["id"]


@pytest.fixture
def combined_run(client, dataset, mbs_dataset):
    ids = {"holdings": up(client, "holdings", "holdings_combined.csv"),
           "vendors": [up(client, "vendor_secondary", "vendor_b.csv", "VendorB"),
                       up(client, "vendor_secondary", "mbs_vendor_factset.csv", "FactSet"),
                       up(client, "vendor_secondary", "mbs_vendor_pricing.csv", "PricingVendor")],
           "history": up(client, "price_history", "price_history.csv"),
           "ledger": up(client, "ledger", "mbs_ledger.csv")}
    d = client.post("/api/documents", data={"cusip": "MULTIPLE", "doc_kind": "pool_disclosure", "asset_class": "agency_mbs"},
                    files={"file": ("mbs_pool_disclosure.csv", (SYN / "mbs_pool_disclosure.csv").read_bytes(), "text/csv")})
    assert d.status_code == 200, d.text
    run = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": ids["holdings"],
                                                "vendor_batch_ids": ids["vendors"], "history_batch_id": ids["history"],
                                                "ledger_batch_id": ids["ledger"]})
    assert run.status_code == 200, run.text
    return run.json()


def test_one_run_covers_both_asset_classes(client, combined_run, dataset, mbs_dataset):
    flags = combined_run["flags"]
    by = {}
    for f in flags:
        by.setdefault(f["cusip"], set()).add(f["rule"])
    for d in [*dataset.defects, *mbs_dataset.defects]:
        assert set(d.expected_rules) <= by.get(d.cusip, set()), d.defect_id
    assert flags[0]["rule"] == "cash_reconciliation"
    view = client.get(f"/api/screen-runs/{combined_run['id']}/cusips").json()["cusips"]
    classes = {c["asset_class"] for c in view}
    assert classes == {"muni", "agency_mbs"}


def test_m01_finding_from_supplement_disclosure_and_cash(client, combined_run, mbs_dataset):
    d = next(x for x in mbs_dataset.defects if x.defect_id.startswith("M01"))
    h = next(x for x in mbs_dataset.holdings if x.position.cusip == d.cusip)
    pdf = (OS / f"SUPP_{d.cusip}.pdf").read_bytes()
    r = client.post(f"/api/screen-runs/{combined_run['id']}/cusips/{d.cusip}/official-statement",
                    files={"file": ("supp.pdf", pdf, "application/pdf")}).json()
    assert r["error"] is None and r["extraction"]["status"] == "ok", r
    assert r["document"]["doc_kind"] == "oc_supplement" and r["document"]["asset_class"] == "agency_mbs"
    f = r["finding"]
    assert f["asset_class"] == "agency_mbs" and f["income_impact_usd"] > 10_000
    assert "0.000%" in f["headline"] and "confirmed by cash" in f["headline"]
    assert "FactSet: coupon BLANK" in f["narrative"]["vendor_says"]
    nc = next(row for row in f["comparison"] if row["field"].startswith("Net coupon ("))
    assert nc["vendor"] == "0.000%" and nc["locator"].startswith("mbs_pool_disclosure.csv:row") and nc["locator"].endswith("net coupon") and nc["page"] is None
    cur = next(o for o in h.observations if o.month.isoformat() == "2026-11-01")
    assert nc["document"] == f"{cur.net_coupon:.3%}"
    metrics = {m["label"]: m["value"] for m in f["narrative"]["metrics"]}
    assert metrics["Coupon · book"] == 0.0 and metrics["Net coupon · document"] == pytest.approx(cur.net_coupon)
    sched = f["narrative"]["schedule"]
    assert len(sched) == 13 and all(row["booked"] == 0 for row in sched)
    assert sum(1 for row in sched if row["cash"] is not None) == 12

    # approve and export: export carries the asset class and the BLANK/0 distinction
    client.post(f"/api/findings/{f['id']}/actions", json={"action": "approve", "comment": "book WAC coupon"})
    csv_text = client.get("/api/exports/approved.csv").text
    assert d.cusip in csv_text and "agency_mbs" in csv_text


def test_m02_fixed_rate_finding(client, combined_run, mbs_dataset):
    d = next(x for x in mbs_dataset.defects if x.defect_id.startswith("M02"))
    pdf = (OS / f"SUPP_{d.cusip}.pdf").read_bytes()
    r = client.post(f"/api/screen-runs/{combined_run['id']}/cusips/{d.cusip}/official-statement",
                    files={"file": ("supp.pdf", pdf, "application/pdf")}).json()
    f = r["finding"]
    assert "coupon 3.500%" in f["headline"] and "5.500%" in f["headline"]
    # 12 months booked at 3.5% instead of 5.5%: understatement ~ 2/5.5 of the interest earned
    assert f["income_impact_usd"] > 0


def test_unsupported_product_refused_with_reason(client, mbs_dataset):
    """The book says the security is a CMO tranche: the finding is refused with the reason, not computed."""
    m02 = next(x for x in mbs_dataset.defects if x.defect_id.startswith("M02")).cusip
    rows = (SYN / "mbs_holdings.csv").read_text().splitlines()
    rows = [rows[0]] + [r.replace(",pass_through,", ",cmo,") for r in rows[1:] if m02 in r]
    hid = client.post("/api/uploads/holdings", files={"file": ("h.csv", "\n".join(rows) + "\n", "text/csv")}).json()
    run = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid["batch"]["id"]}).json()
    r = client.post(f"/api/screen-runs/{run['id']}/cusips/{m02}/official-statement",
                    files={"file": ("supp.pdf", (OS / f"SUPP_{m02}.pdf").read_bytes(), "application/pdf")}).json()
    assert r["extraction"]["status"] == "ok" and r["finding"] is None
    assert r["error"].startswith("unsupported: CMO tranches are not implemented")
