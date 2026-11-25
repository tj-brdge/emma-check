#!/usr/bin/env python3
"""Load the synthetic muni + agency MBS universe through the HTTP API (as a user would) and
analyse the sample offering documents. Standard library only - runs with any Python 3.8+.

Usage: python3 backend/scripts/demo_seed.py [--api URL] [--user NAME]
Default --api is the docker compose stack (http://localhost:18080); for a local uvicorn use
--api http://localhost:8000.
"""
from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from urllib import error, request

DATA = Path(__file__).resolve().parents[2] / "data"


class Api:
    def __init__(self, base: str, user: str):
        self.base, self.user = base.rstrip("/"), user

    def _send(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None):
        req = request.Request(self.base + path, data=body, method=method, headers={"X-User": self.user})
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with request.urlopen(req, timeout=900) as r:
                return json.loads(r.read().decode() or "null")
        except error.HTTPError as e:
            text = e.read().decode(errors="replace")
            try:
                detail = json.loads(text).get("detail")
            except ValueError:
                detail = text[:500]
            raise SystemExit(f"{method} {path} -> HTTP {e.code}: {detail}") from None

    def get(self, path):
        return self._send("GET", path)

    def post_json(self, path, payload):
        return self._send("POST", path, json.dumps(payload).encode(), "application/json")

    def post_form(self, path, fields: dict, file_name: str, content: bytes, file_type: str):
        boundary = uuid.uuid4().hex
        parts = []
        for k, v in fields.items():
            if v is not None:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                     f"Content-Type: {file_type}\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        return self._send("POST", path, b"".join(parts), f"multipart/form-data; boundary={boundary}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:18080")
    ap.add_argument("--user", default="demo.loader")
    a = ap.parse_args()
    api = Api(a.api, a.user)
    try:
        request.urlopen(api.base + "/api/health", timeout=10).read()
    except (error.URLError, OSError) as e:
        raise SystemExit(
            f"Terms Check is not reachable at {a.api} ({e}).\n"
            "Start it first:  TERMSCHECK_LLM_MODE=recorded docker compose up --build\n"
            "wait until the 'api' service logs 'Uvicorn running', then re-run this script.\n"
            "If the API runs elsewhere, pass --api, e.g. --api http://localhost:8000") from None
    syn = DATA / "synthetic"

    def upload(kind, fn, vendor=None):
        r = api.post_form(f"/api/uploads/{kind}", {"vendor": vendor}, fn, (syn / fn).read_bytes(), "text/csv")
        print(f"uploaded {fn}: batch {r['batch']['id']}")
        return r["batch"]["id"]

    holdings = upload("holdings", "holdings_combined.csv", "FundAccounting")
    vendors = [upload("vendor_secondary", "vendor_b.csv", "VendorB"),
               upload("vendor_secondary", "mbs_vendor_factset.csv", "FactSet"),
               upload("vendor_secondary", "mbs_vendor_pricing.csv", "PricingVendor")]
    history = upload("price_history", "price_history.csv")
    ledger = upload("ledger", "mbs_ledger.csv")
    d = api.post_form("/api/documents", {"cusip": "MULTIPLE", "doc_kind": "pool_disclosure",
                                         "asset_class": "agency_mbs"},
                      "mbs_pool_disclosure.csv", (syn / "mbs_pool_disclosure.csv").read_bytes(), "text/csv")
    print(f"pool disclosure: document {d['id']}")
    manifest = json.loads((syn / "planted_defects.json").read_text())
    run = api.post_json("/api/screen-runs", {"as_of": manifest["as_of"], "holdings_batch_id": holdings,
                                             "vendor_batch_ids": vendors, "history_batch_id": history,
                                             "ledger_batch_id": ledger})
    print(f"screen run {run['id']}: {run['flag_count']} flags")
    for pdf in sorted((DATA / "sample_os").glob("*.pdf")):
        cusip = pdf.stem.split("_")[1]
        try:
            r = api.post_form(f"/api/screen-runs/{run['id']}/cusips/{cusip}/official-statement", {},
                              pdf.name, pdf.read_bytes(), "application/pdf")
        except SystemExit as e:
            print(f"{cusip}: {e}")
            continue
        f = r.get("finding")
        print(f"{cusip}: extraction {r['extraction']['status']}"
              + (f", finding {f['id']} impact ${f['income_impact_usd']:,.0f}" if f else f", error {r['error']}"))
    print(f"\nDone. Open {a.api.replace('/api', '')} and enter a reviewer name (top right).")


if __name__ == "__main__":
    main()
