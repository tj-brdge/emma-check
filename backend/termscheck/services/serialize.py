"""JSON (de)serialisation helpers for dataclasses stored in JSONB."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any



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
