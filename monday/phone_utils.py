"""Shared phone (E.164) and messenger handle normalization helpers for Stage A1 lead integrity."""
from __future__ import annotations

import re

_ALPHA_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")


def normalize_phone(raw: str | None, default_country: str = "KG") -> str | None:
    """Normalize phone strings into E.164 format without ever raising.

    Supports Kyrgyzstan defaults:
      - +996XXXXXXXXX -> +996XXXXXXXXX
      - 996XXXXXXXXX  -> +996XXXXXXXXX
      - 0XXXXXXXXX    -> +996XXXXXXXXX
    Other international numbers starting with '+' (or '00') pass through if 8..15 digits.
    Invalid inputs return None.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s or _ALPHA_RE.search(s):
        return None

    # Strip whitespace, dashes, parentheses, dots
    compact = re.sub(r"[\s\-().\u00a0]+", "", s)
    if not compact:
        return None

    has_plus = compact.startswith("+")
    if compact.startswith("00") and len(compact) > 2:
        has_plus = True
        compact = "+" + compact[2:]

    if has_plus:
        digits = compact[1:]
        if not digits.isdigit():
            return None
        if digits.startswith("996"):
            return ("+" + digits) if len(digits) == 12 else None
        if 8 <= len(digits) <= 15 and digits[0] != "0":
            return "+" + digits
        return None

    if not compact.isdigit():
        return None

    if default_country == "KG":
        if compact.startswith("996") and len(compact) == 12 and compact[3] != "0":
            return "+" + compact
        if compact.startswith("0") and len(compact) == 10 and compact[1] != "0":
            return "+996" + compact[1:]

    return None


def normalize_messenger(raw: str | None) -> str | None:
    """Canonicalize messenger handles (@user, t.me/user, instagram.com/user, wa.me/...) for dedupe."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s:
        return None
    for prefix in (
        "https://",
        "http://",
        "t.me/",
        "telegram.me/",
        "www.instagram.com/",
        "instagram.com/",
        "wa.me/",
    ):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    s = s.strip().lstrip("@").strip("/")
    s = re.sub(r"\s+", "", s)
    return s[:120] or None
