"""Page text extraction and relevance prefiltering. Pure functions over bytes/strings."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader

KEYWORDS = {
    r"deferred interest": 5, r"capital appreciation": 5, r"accret": 4, r"compound": 4,
    r"conversion date": 4, r"convertible": 3, r"360-day year": 4, r"30-day months": 4,
    r"day count": 3, r"interest (?:is|shall be|will be) payable": 4, r"dated date": 3,
    r"interest payment date": 3, r"redemption": 2, r"maturity schedule": 4, r"cusip": 2,
    r"interest rate": 2, r"per annum": 3, r"payable semiannually": 3, r"zero coupon": 4,
}


@dataclass(frozen=True)
class PageSelection:
    pages: list[int]                 # 1-based, ascending
    total_pages: int
    reasons: dict[int, list[str]]
    truncated: bool                  # True if relevant pages were left out to fit the budget


def extract_pages(content: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(content))
    return [(p.extract_text() or "") for p in reader.pages]


def select_pages(pages: list[str], cusip: str, max_pages: int) -> PageSelection:
    """Choose which pages to send. Small documents go whole. Larger ones: cover pages, pages
    naming the CUSIP, then pages ranked by interest-terms keywords, up to ``max_pages``."""
    n = len(pages)
    if n <= max_pages:
        return PageSelection(list(range(1, n + 1)), n, {i: ["whole document"] for i in range(1, n + 1)}, False)
    reasons: dict[int, list[str]] = {}
    scores: dict[int, float] = {}
    for i, text in enumerate(pages, start=1):
        low = text.lower()
        sc = 0.0
        for pat, w in KEYWORDS.items():
            k = len(re.findall(pat, low))
            if k:
                sc += w * min(k, 5)
                reasons.setdefault(i, []).append(pat)
        if cusip.upper() in text.upper():
            sc += 1000
            reasons.setdefault(i, []).append("names CUSIP")
        if i <= 3:
            sc += 500
            reasons.setdefault(i, []).append("cover")
        scores[i] = sc
    ranked = sorted((i for i in scores if scores[i] > 0), key=lambda i: (-scores[i], i))
    chosen = sorted(ranked[:max_pages])
    return PageSelection(chosen, n, {i: reasons[i] for i in chosen}, len(ranked) > max_pages)


def page_tagged_text(pages: list[str], selection: list[int]) -> str:
    return "\n".join(f'<page number="{i}">\n{pages[i - 1].strip()}\n</page>' for i in selection)
