#!/usr/bin/env python3
"""Write the synthetic dataset to data/synthetic/ (CSV inputs + planted-defect manifest)."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from termscheck.ingest import history_csv, holdings_csv, ledger_csv, vendor_csv
from termscheck.plugins.agency_mbs import synthetic as mbs
from termscheck.plugins.muni.synthetic import SEED, generate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "data" / "synthetic"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    ds = generate(a.seed)
    (out / "holdings_vendor_a.csv").write_text(holdings_csv([(h.position, h.vendor_a) for h in ds.holdings]))
    (out / "vendor_b.csv").write_text(vendor_csv([h.vendor_b for h in ds.holdings if h.vendor_b]))
    (out / "price_history.csv").write_text(history_csv([p for h in ds.holdings for p in h.history]))
    manifest = {
        "seed": a.seed, "as_of": ds.as_of.isoformat(), "holdings": len(ds.holdings),
        "defects": [{**{k: v for k, v in asdict(d).items() if k != "true_terms"},
                     "true_terms": {k: (v.isoformat() if hasattr(v, "isoformat") else
                                        (v.value if hasattr(v, "value") else v))
                                    for k, v in asdict(d.true_terms).items()}}
                    for d in ds.defects],
    }
    # Agency MBS
    m = mbs.generate()
    (out / "mbs_holdings.csv").write_text(holdings_csv([(h.position, h.book) for h in m.holdings]))
    for name, fn in (("FactSet", "mbs_vendor_factset.csv"), ("PricingVendor", "mbs_vendor_pricing.csv")):
        (out / fn).write_text(vendor_csv([h.vendors[name] for h in m.holdings]))
    (out / "mbs_ledger.csv").write_text(ledger_csv([e for h in m.holdings for e in h.ledger]))
    (out / "mbs_pool_disclosure.csv").write_text(mbs.disclosure_csv(m))
    # One book-of-record file covering both asset classes (what a fund's security master looks like)
    from dataclasses import replace as _r
    combined = [(h.position, _r(h.vendor_a, vendor="FundAccounting")) for h in ds.holdings] + \
               [(h.position, h.book) for h in m.holdings]
    (out / "holdings_combined.csv").write_text(holdings_csv(combined))
    manifest["mbs"] = {"seed": mbs.SEED, "holdings": len(m.holdings),
                       "defects": [vars(d) for d in m.defects], "traps": m.traps}
    (out / "planted_defects.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(ds.holdings)} muni + {len(m.holdings)} MBS holdings, "
          f"{len(ds.defects)} + {len(m.defects)} planted defects to {out}")


if __name__ == "__main__":
    main()
