"""Security identifier helpers."""
from __future__ import annotations


def cusip_check_digit(base8: str) -> str:
    total = 0
    for i, ch in enumerate(base8):
        if ch.isdigit():
            v = int(ch)
        elif ch.isalpha():
            v = ord(ch.upper()) - 55
        else:
            v = {"*": 36, "@": 37, "#": 38}[ch]
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return str((10 - total % 10) % 10)


def is_valid_cusip(c: str) -> bool:
    return len(c) == 9 and c.isalnum() and cusip_check_digit(c[:8].upper()) == c[8]
