"""Load the synthetic dataset through the HTTP API (as a user would) and analyse the sample
official statements. Usage: python scripts/demo_seed.py [--api http://localhost:8000]"""
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
    c = httpx.Client(base_url=a.api, headers={"X-User": a.user}, timeout=600)
    syn = DATA / "synthetic"
    ids = {}
    for kind, fn, vendor in [("holdings", "holdings_vendor_a.csv", "VendorA"),
                             ("vendor_secondary", "vendor_b.csv", "VendorB"),
                             ("price_history", "price_history.csv", None)]:
        r = c.post(f"/api/uploads/{kind}", files={"file": (fn, (syn / fn).read_bytes(), "text/csv")},
                   data={"vendor": vendor} if vendor else {})
        r.raise_for_status()
        ids[kind] = r.json()["batch"]["id"]
        print(f"uploaded {fn}: batch {ids[kind]}")
    manifest = json.loads((syn / "planted_defects.json").read_text())
    run = c.post("/api/screen-runs", json={"as_of": manifest["as_of"], "holdings_batch_id": ids["holdings"],
                                          "secondary_batch_id": ids["vendor_secondary"],
                                          "history_batch_id": ids["price_history"]}).json()
    print(f"screen run {run['id']}: {run['flag_count']} flags")
    for pdf in sorted((DATA / "sample_os").glob("OS_*.pdf")):
        cusip = pdf.stem.split("_")[1]
        r = c.post(f"/api/screen-runs/{run['id']}/cusips/{cusip}/official-statement",
                   files={"file": (pdf.name, pdf.read_bytes(), "application/pdf")}).json()
        f = r.get("finding")
        print(f"{cusip}: extraction {r['extraction']['status']}"
              + (f", finding {f['id']} impact ${f['income_impact_usd']:,.0f}" if f else f", error {r['error']}"))


if __name__ == "__main__":
    main()
