from datetime import date

import pytest

from termscheck.ingest import parse_ledger
from termscheck.plugins.agency_mbs.disclosure import parse_pool_disclosure

C1, C2 = "3137MBS09", "3137MBS17"


# ---------------------------------------------------------------- ledger
def test_ledger_parses_and_keeps_blank_booked_income_blank():
    r = parse_ledger("cusip,payment_date,cash_received,type,booked_income\n"
                     f"{C1},2026-10-15,3380.88,interest,\n{C1},2026-10-15,10000,principal,0\n")
    assert r.ok, r.errors
    i, p = r.ledger
    assert i.kind == "interest" and i.cash == pytest.approx(3380.88) and i.booked_income is None
    assert p.booked_income == 0.0 and i.portfolio == "DEFAULT" and i.entry_date == date(2026, 10, 15)


@pytest.mark.parametrize("row,col", [(f"{C1},2026-10-15,,interest", "cash"),
                                     (f"{C1},2026-10-15,100,coupon", "type"),
                                     (f"XXXXXXXXX,2026-10-15,100,interest", "cusip")])
def test_ledger_rejects_bad_rows(row, col):
    r = parse_ledger("cusip,entry_date,cash,type\n" + row + "\n")
    assert not r.ok and r.errors[0].column == col


# ---------------------------------------------------------------- pool disclosure
def test_disclosure_parse_with_locators_and_blanks():
    text = ("CUSIP|Factor Month|Pool Factor|Net Coupon|WAC\n"
            f"{C1}|2026-09|0.8700000000|4.810|5.420\n"
            f"{C1}|202610|0.8600000000||5.405\n"
            f"{C2}|11/2026|0.5000000000|3.500|4.100\n")
    p = parse_pool_disclosure("pools.txt", text)
    assert not p.errors, p.errors
    obs = p.by_cusip()[C1]
    assert [o.month for o in obs] == [date(2026, 9, 1), date(2026, 10, 1)]
    assert obs[0].net_coupon == pytest.approx(0.0481) and obs[1].net_coupon is None   # blank stays blank
    assert obs[0].source == "pools.txt:row 1"
    assert p.by_cusip()[C2][0].month == date(2026, 11, 1)


@pytest.mark.parametrize("text,msg", [
    ("cusip,month\nX,2026-01\n", "factor"),
    (f"cusip,month,factor\n{C1},Jan 2026,0.9\n", "unrecognised month"),
    (f"cusip,month,factor\n{C1},2026-01,2.5\n", "out of range"),
    (f"cusip,month,factor\n{C1[:8]}X,2026-01,0.9\n", "invalid CUSIP"),
])
def test_disclosure_rejections(text, msg):
    assert any(msg in e for e in parse_pool_disclosure("f.csv", text).errors)


# ---------------------------------------------------------------- API round trip
MBS_HOLDINGS = ("portfolio,cusip,description,par,price,price_convention,coupon,accrual_type,maturity_date,"
                "issue_date,rating,sector,state,payment_frequency,asset_class,product_type,factor,factor_date,"
                "payment_delay_days,rate_type\n"
                f"MBS-01,{C1},FHLMC Pool test,1000000,101.25,clean,,,2051-01-01,2021-01-01,,,,12,agency_mbs,"
                "pass_through,0.85,2026-11-01,45,wac\n")


@pytest.mark.db
def test_ledger_and_disclosure_drive_mbs_cash_reconciliation(client, engine):
    from sqlalchemy import text
    hid = client.post("/api/uploads/holdings", files={"file": ("h.csv", MBS_HOLDINGS, "text/csv")}).json()["batch"]["id"]
    led = "portfolio,cusip,entry_date,cash,type\n" + "".join(
        f"MBS-01,{C1},{d},{amt},interest\n" for d, amt in
        [("2026-10-15", "3486.75"), ("2026-11-16", "3436.42")])   # Sep, Oct interest; Nov 15 is a Sunday
    lid = client.post("/api/uploads/ledger", files={"file": ("l.csv", led, "text/csv")})
    assert lid.status_code == 200, lid.text
    disc = ("cusip,factor_month,factor,net_coupon\n"
            f"{C1},2026-09,0.87,4.810\n{C1},2026-10,0.86,4.795\n{C1},2026-11,0.85,4.773\n")
    d = client.post("/api/documents", data={"cusip": C1, "doc_kind": "pool_disclosure"},
                    files={"file": ("pool.csv", disc.encode(), "text/csv")})
    assert d.status_code == 200, d.text
    assert d.json()["doc_kind"] == "pool_disclosure" and d.json()["asset_class"] == "agency_mbs"
    obs = client.get(f"/api/cusips/{C1}/disclosures").json()
    assert obs[0]["locator"] == "pool.csv:row 1" and len(obs) == 3
    run = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid,
                                                "ledger_batch_id": lid.json()["batch"]["id"]}).json()
    assert run["ledger_batch_id"] and run["disclosure_document_ids"] == [d.json()["id"]]
    cash = next(f for f in run["flags"] if f["rule"] == "cash_reconciliation")
    c = cash["computed"]
    assert c["booked_total"] == 0 and c["book_rate"] == "BLANK"
    # Sep: 3,486.75 x 12 / (1,000,000 x 0.87) = 4.8093% ; Oct: 3,436.42 x 12 / 860,000 = 4.7950%
    assert [round(r["implied_rate"], 5) for r in c["receipts"]] == [0.04809, 0.04795]
    assert c["receipts"][0]["period_start"] == "2026-09-01" and not c["assumptions"]
    rules = {f["rule"] for f in run["flags"]}
    assert {"cash_reconciliation", "frequency_contradiction", "null_vs_zero"} <= rules
    assert run["flags"][0]["rule"] == "cash_reconciliation"
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM ledger_entry"))


@pytest.mark.db
def test_bad_disclosure_rejected(client):
    r = client.post("/api/documents", data={"cusip": C1, "doc_kind": "pool_disclosure", "asset_class": "agency_mbs"},
                    files={"file": ("p.csv", b"cusip,month\nX,1\n", "text/csv")})
    assert r.status_code == 422 and "rejected" in r.text
