"""Load the synthetic muni + agency MBS universe through the HTTP API (as a user would) and
analyse the sample offering documents. Usage: python scripts/demo_seed.py [--api URL] [--user NAME]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[2] / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--user", default="demo.loader")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.api, headers={"X-User": a.user}, timeout=900)
    syn = DATA / "synthetic"

    def call(resp):
        try:
            body = resp.json()
        except ValueError:
            raise SystemExit(f"{resp.request.method} {resp.request.url} -> HTTP {resp.status_code}: {resp.text[:500]}")
        if resp.status_code >= 400:
            raise SystemExit(f"{resp.request.method} {resp.request.url} -> HTTP {resp.status_code}: {body.get('detail')}")
        return body

    def upload(kind, fn, vendor=None):
        r = call(c.post(f"/api/uploads/{kind}", files={"file": (fn, (syn / fn).read_bytes(), "text/csv")},
                        data={"vendor": vendor} if vendor else {}))
        bid = r["batch"]["id"]
        print(f"uploaded {fn}: batch {bid}")
        return bid

    holdings = upload("holdings", "holdings_combined.csv", "FundAccounting")
    vendors = [upload("vendor_secondary", "vendor_b.csv", "VendorB"),
               upload("vendor_secondary", "mbs_vendor_factset.csv", "FactSet"),
               upload("vendor_secondary", "mbs_vendor_pricing.csv", "PricingVendor")]
    history = upload("price_history", "price_history.csv")
    ledger = upload("ledger", "mbs_ledger.csv")
    d = c.post("/api/documents", data={"cusip": "MULTIPLE", "doc_kind": "pool_disclosure", "asset_class": "agency_mbs"},
               files={"file": ("mbs_pool_disclosure.csv", (syn / "mbs_pool_disclosure.csv").read_bytes(), "text/csv")})
    print(f"pool disclosure: document {call(d)['id']}")
    manifest = json.loads((syn / "planted_defects.json").read_text())
    run = call(c.post("/api/screen-runs", json={"as_of": manifest["as_of"], "holdings_batch_id": holdings,
                                               "vendor_batch_ids": vendors, "history_batch_id": history,
                                               "ledger_batch_id": ledger}))
    print(f"screen run {run['id']}: {run['flag_count']} flags")
    for pdf in sorted((DATA / "sample_os").glob("*.pdf")):
        cusip = pdf.stem.split("_")[1]
        try:
            r = call(c.post(f"/api/screen-runs/{run['id']}/cusips/{cusip}/official-statement",
                            files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}))
        except SystemExit as e:
            print(f"{cusip}: {e}")
            continue
        f = r.get("finding")
        print(f"{cusip}: extraction {r['extraction']['status']}"
              + (f", finding {f['id']} impact ${f['income_impact_usd']:,.0f}" if f else f", error {r['error']}"))


if __name__ == "__main__":
    main()
