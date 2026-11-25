"""Deterministic citation verification: does each excerpt actually appear on the cited page?

Matching is done on normalised text (case, whitespace, quotes, dashes, line-break hyphens).
Exact substring -> "verified"; best sliding-window similarity >= threshold -> "fuzzy";
found on a different page -> "wrong_page"; otherwise "not_found".
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

FUZZY_THRESHOLD = 0.90

_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
                        "—": "-", " ": " ", "‑": "-"})


def normalise(s: str) -> str:
    s = s.translate(_TRANS).lower()
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)  # de-hyphenate line breaks
    s = re.sub(r"[^\w%$.,'\"()/-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class CitationCheck:
    field: str
    status: str                    # verified | fuzzy | wrong_page | not_found | missing_citation | absent
    page: int | None
    score: float
    found_on_page: int | None = None
    value_in_excerpt: bool | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("verified", "fuzzy", "absent")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"ok": self.ok}


def _best_window(needle: str, hay: str) -> float:
    if not needle or not hay:
        return 0.0
    if needle in hay:
        return 1.0
    n = len(needle)
    best = 0.0
    step = max(1, n // 8)
    for i in range(0, max(1, len(hay) - n + 1), step):
        r = SequenceMatcher(None, needle, hay[i:i + n + n // 10], autojunk=False).ratio()
        if r > best:
            best = r
    return best


def check_excerpt(field: str, page: int | None, excerpt: str | None, has_value: bool,
                  pages: list[str], value_repr: list[str] | None = None) -> CitationCheck:
    if not has_value:
        return CitationCheck(field, "absent", page, 0.0)
    if page is None or not excerpt or not excerpt.strip():
        return CitationCheck(field, "missing_citation", page, 0.0)
    nx = normalise(excerpt)
    vin = None
    if value_repr:
        vin = any(normalise(v) in nx for v in value_repr if v)
    if not (1 <= page <= len(pages)):
        return CitationCheck(field, "not_found", page, 0.0, value_in_excerpt=vin)
    score = _best_window(nx, normalise(pages[page - 1]))
    if score == 1.0:
        return CitationCheck(field, "verified", page, 1.0, value_in_excerpt=vin)
    if score >= FUZZY_THRESHOLD:
        return CitationCheck(field, "fuzzy", page, score, value_in_excerpt=vin)
    others = [(_best_window(nx, normalise(t)), i) for i, t in enumerate(pages, start=1) if i != page]
    best, where = max(others, default=(0.0, None))
    if best >= FUZZY_THRESHOLD:
        return CitationCheck(field, "wrong_page", page, score, found_on_page=where, value_in_excerpt=vin)
    return CitationCheck(field, "not_found", page, score, value_in_excerpt=vin)
