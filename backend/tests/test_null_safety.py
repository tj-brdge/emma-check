"""A blank vendor field is unknown, not zero. It must stay distinguishable end to end."""
import re
from pathlib import Path

import pytest

from termscheck.core.records import ABSENT, BLANK, VALUE
from termscheck.ingest import parse_holdings, parse_vendor

HDR = ("cusip,description,par,price,price_convention,coupon,accrual_type,maturity_date,issue_date,"
       "rating,sector,state,payment_frequency\n")
ROW = "Q4TWLP484,Test bond,1000000,99.5,clean,{coupon},fixed,2034-07-01,2019-07-01,AA,General Obligation,NY,{freq}\n"


@pytest.mark.parametrize("cell,state,value", [
    ("", BLANK, None), ("NA", BLANK, None), ("--", BLANK, None), ("n/a", BLANK, None),
    ("0", VALUE, 0.0), ("0.000", VALUE, 0.0), ("4.773", VALUE, 0.04773),
])
def test_coupon_cell_states(cell, state, value):
    r = parse_holdings(HDR + ROW.format(coupon=cell, freq="12"))
    assert r.ok, r.errors
    rec = r.records[0]
    assert rec.state_of("coupon") == state
    assert rec.coupon == (pytest.approx(value) if value else value)
    assert rec.raw["coupon"] == cell                      # original text kept
    if state == BLANK:
        assert rec.coupon is None and not rec.is_zero("coupon")
    else:
        assert rec.is_zero("coupon") == (value == 0.0)


def test_absent_column_is_not_blank():
    hdr = HDR.replace(",payment_frequency", "")
    r = parse_holdings(hdr + ROW.format(coupon="5", freq="").rsplit(",", 1)[0] + "\n")
    assert r.ok, r.errors
    assert r.records[0].state_of("payment_frequency") == ABSENT


def test_blank_cells_do_not_reject_file_but_required_ones_do():
    assert parse_vendor(HDR.replace("par,", "") + ROW.format(coupon="", freq="").replace("1000000,", ""), "FactSet").ok
    bad = ROW.format(coupon="5", freq="2").replace("99.5", "")
    r = parse_holdings(HDR + bad)
    assert not r.ok and r.errors[0].column == "price"


def test_no_coercion_patterns_in_source():
    """Static guard: no `x or 0` / `fillna(0)` anywhere, and no `.get(<term field>, 0)`."""
    terms = "coupon|rate|factor|payment_frequency|vendor_yield|payment_delay_days|price|par|cash|booked_income"
    pat = re.compile(r"\bor 0(\.0)?\b|fillna\(0|\.get\(\s*['\"](" + terms + r")['\"]\s*,\s*0(\.0)?\)")
    hits = []
    for f in (Path(__file__).resolve().parents[1] / "termscheck").rglob("*.py"):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if pat.search(line.split("#")[0]):
                hits.append(f"{f.name}:{i}: {line.strip()}")
    assert not hits, hits


@pytest.mark.db
def test_blank_coupon_survives_database_screens_and_api(client, engine):
    from sqlalchemy import text
    csv = HDR + ROW.format(coupon="", freq="12")
    hid = client.post("/api/uploads/holdings", files={"file": ("h.csv", csv, "text/csv")}).json()["batch"]["id"]
    vend = (HDR.replace("par,", "") + ROW.format(coupon="0", freq="12").replace("1000000,", ""))
    vid = client.post("/api/uploads/vendor_secondary", files={"file": ("v.csv", vend, "text/csv")},
                      data={"vendor": "FactSet"}).json()["batch"]["id"]
    with engine.connect() as c:
        row = c.execute(text("select coupon, field_states->>'coupon', raw->>'coupon' from vendor_terms "
                             f"where batch_id={hid}")).one()
    assert row == (None, "blank", "")
    run = client.post("/api/screen-runs", json={"as_of": "2026-11-30", "holdings_batch_id": hid,
                                                "vendor_batch_ids": [vid]})
    assert run.status_code == 200, run.text
    flags = run.json()["flags"]
    dis = next(f for f in flags if f["rule"] == "vendor_disagreement")
    assert dis["computed"]["differences"]["coupon"] == {"FundAccounting": "BLANK", "FactSet": 0.0}
    body = client.get(f"/api/screen-runs/{run.json()['id']}/cusips").json()
    assert body["cusips"][0]["coupon"] is None
    ev = client.get("/api/audit?event_type=upload.accepted").json()
    assert any(e["payload"].get("blank_cells", {}).get("coupon") == 1 for e in ev)
