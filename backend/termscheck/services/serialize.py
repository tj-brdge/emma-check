"""JSON (de)serialisation helpers for dataclasses stored in JSONB."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from ..bondmath import DayCount, InterestTerms, InterestType


def jsonable(x: Any) -> Any:
    if is_dataclass(x) and not isinstance(x, type):
        return jsonable(asdict(x))
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    return x


def terms_from_dict(d: dict) -> InterestTerms:
    def dt(k):
        return date.fromisoformat(d[k]) if d.get(k) else None
    return InterestTerms(
        interest_type=InterestType(d["interest_type"]), rate=d["rate"], dated_date=dt("dated_date"),
        maturity_date=dt("maturity_date"), day_count=DayCount(d["day_count"]),
        payment_frequency=d["payment_frequency"], compounding_frequency=d["compounding_frequency"],
        first_coupon_date=dt("first_coupon_date"), first_compounding_date=dt("first_compounding_date"),
        conversion_date=dt("conversion_date"))
