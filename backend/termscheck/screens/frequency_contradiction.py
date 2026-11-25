"""Payment frequency contradiction: a source says the security pays interest periodically
(frequency > 0) but carries a zero or blank coupon.

Explicitly non-paying labels (zero / CAB / accreting / deferred accrual types, PO product type)
are still flagged - the feed is self-contradictory - but at low severity.
"""
from __future__ import annotations

from termscheck.core.records import Flag, ScreenInput
from termscheck.screens.base import ScreenContext, clamp_severity
from termscheck.screens.config import ScreenConfig

NON_PAYING_LABELS = {"zero", "cab", "accreting", "capital_appreciation", "deferred", "deferred_interest"}


class FrequencyContradictionScreen:
    confidence = 0.85
    rule = "frequency_contradiction"

    def run(self, data: ScreenInput, config: ScreenConfig, ctx: ScreenContext) -> list[Flag]:
        flags: list[Flag] = []
        for cusip in data.primary:
            hits = []
            for r in data.sources_for(cusip):
                if r.payment_frequency is None or r.payment_frequency <= 0:
                    continue
                if r.coupon is None or r.coupon == 0:
                    labelled = ((r.accrual_type or "") in NON_PAYING_LABELS) or r.product_type == "po"
                    hits.append({"source": r.vendor, "payment_frequency": r.payment_frequency,
                                 "coupon": "BLANK" if r.coupon is None else 0.0,
                                 "accrual_type": r.accrual_type, "product_type": r.product_type,
                                 "explicitly_non_paying": labelled})
            if not hits:
                continue
            unexplained = [h for h in hits if not h["explicitly_non_paying"]]
            sev = clamp_severity(70 + 5 * (len(unexplained) - 1)) if unexplained else 25
            msg = "; ".join(f"{h['source']}: pays {h['payment_frequency']}x/yr with coupon {h['coupon']}"
                            + (" (labelled non-paying)" if h["explicitly_non_paying"] else "") for h in hits)
            flags.append(Flag(self.rule, cusip, sev, msg + ".", {"sources": [h["source"] for h in hits]},
                              {"contradictions": hits, "unexplained": len(unexplained)}))
        return flags
