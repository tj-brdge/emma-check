from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..db.models import Computation, Extraction, Finding, Holding, ReviewAction, VendorTerms
from ..review import apply, rows_to_csv
from .extraction import citation_index


def act(session: Session, *, finding_id: int, action: str, comment: str | None, user: str) -> ReviewAction:
    f = session.get(Finding, finding_id, with_for_update=True)
    if f is None:
        raise LookupError("finding not found")
    new = apply(f.status, action, comment)
    ra = ReviewAction(finding_id=f.id, action=action, from_status=f.status, to_status=new.value,
                      comment=(comment or None), actor=user)
    session.add(ra)
    f.status = new.value
    session.flush()
    record(session, actor=user, event_type=f"review.{action}", entity_type="finding", entity_id=f.id,
           payload={"review_action_id": ra.id, "cusip": f.cusip, "from_status": ra.from_status,
                    "to_status": ra.to_status, "comment": ra.comment, "income_impact_usd": f.income_impact_usd})
    return ra


def history(session: Session, finding_id: int) -> list[ReviewAction]:
    return list(session.scalars(select(ReviewAction).where(ReviewAction.finding_id == finding_id)
                                .order_by(ReviewAction.id)))


def approved_rows(session: Session) -> list[dict]:
    rows = []
    for f in session.scalars(select(Finding).where(Finding.status == "approved").order_by(Finding.id)):
        last = session.scalars(select(ReviewAction).where(ReviewAction.finding_id == f.id,
                                                          ReviewAction.action == "approve")
                               .order_by(ReviewAction.id.desc())).first()
        ex = session.get(Extraction, f.extraction_id)
        terms = ex.interest_terms or {}
        cites = citation_index(ex)
        cite_txt = "; ".join(f"{k} p.{v['page']}" for k, v in cites.items() if v.get("page"))
        for c in f.computations:
            h = session.get(Holding, c.holding_id)
            vt = session.scalars(select(VendorTerms).where(VendorTerms.batch_id == h.batch_id,
                                                           VendorTerms.cusip == f.cusip)).first()
            o = c.outputs
            rows.append({
                "finding_id": f.id, "cusip": f.cusip, "description": f.description, "as_of": f.as_of.isoformat(),
                "portfolio": h.portfolio, "par": f"{h.par:.2f}",
                "vendor_coupon_pct": f"{vt.coupon * 100:.4f}", "vendor_accrual_type": vt.accrual_type,
                "vendor_price": f"{vt.price:.6f}", "vendor_price_convention": vt.price_convention,
                "document_interest_type": terms.get("interest_type"),
                "document_rate_pct": f"{terms.get('rate', 0) * 100:.4f}",
                "document_compounding": terms.get("compounding_frequency"),
                "document_day_count": terms.get("day_count"),
                "document_accrual_start": terms.get("dated_date"), "document_maturity": terms.get("maturity_date"),
                "accreted_value_per_100": _f(o.get("accreted_value")),
                "accrued_interest_per_100": _f(o.get("true_accrued")),
                "correct_clean_per_100": _f(o.get("correct_clean")),
                "correct_dirty_per_100": _f(o.get("correct_dirty")),
                "unbooked_income_usd": _f(o.get("unbooked_income_usd"), 2),
                "run_rate_gap_usd_12m": _f(o.get("run_rate_gap_usd"), 2),
                "unbooked_since_acquisition_usd": _f(o.get("unbooked_window_usd"), 2),
                "citations": cite_txt,
                "approved_by": last.actor if last else None,
                "approved_at": last.at.isoformat() if last else None,
                "approval_comment": last.comment if last else None,
                "finding_headline": f.headline,
            })
    return rows


def approved_csv(session: Session, user: str) -> str:
    import hashlib
    rows = approved_rows(session)
    body = rows_to_csv(rows)
    record(session, actor=user, event_type="export.approved_csv", entity_type="export",
           entity_id=hashlib.sha256(body.encode()).hexdigest()[:16],
           payload={"rows": len(rows), "finding_ids": sorted({r["finding_id"] for r in rows}),
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "income_impact_usd": round(sum(float(r["unbooked_income_usd"] or 0) for r in rows), 2)})
    return body


def _f(x, nd: int = 6):
    return None if x is None else f"{x:.{nd}f}"
