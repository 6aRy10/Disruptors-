from __future__ import annotations

import re
from datetime import datetime


_CAPACITY_PATTERNS = [
    re.compile(
        r"(?i)\b(?:current\s+)?capacity\b[^\d]{0,40}"
        r"(?P<value>\d[\d,]*(?:\.\d+)?\s*[kK]?)"
    ),
    re.compile(
        r"(?i)(?P<value>\d[\d,]*(?:\.\d+)?\s*[kK]?)"
        r"\s*(?:pairs|units|pieces|pcs)\s*(?:per|/)\s*week\b"
    ),
]


def _parse_quantity(token: str) -> int:
    text = token.replace(",", "").replace(" ", "")
    multiplier = 1
    if text.lower().endswith("k"):
        multiplier = 1000
        text = text[:-1]
    value = float(text) * multiplier
    if value < 0:
        raise ValueError("capacity cannot be negative")
    return int(round(value))


def _effective_until(text: str) -> str | None:
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        return iso.group(1)

    named = re.search(
        r"(?i)\b(?:until|through|to)\s+"
        r"(\d{1,2})\s+"
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})\b",
        text,
    )
    if named:
        raw = " ".join(named.groups())
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
    return None


def parse_supplier_reply(text: str) -> dict:
    """Parse capacity evidence conservatively.

    The parser returns structured data for review. It never updates state.
    Ambiguous free text is rejected instead of selecting an arbitrary number.
    """
    raw = str(text or "").strip()
    if not raw:
        return {
            "ok": False,
            "reason": "Empty supplier reply",
            "requires_confirmation": False,
            "raw_message": text,
        }

    matches: list[tuple[int, str]] = []
    for pattern_index, pattern in enumerate(_CAPACITY_PATTERNS):
        for match in pattern.finditer(raw):
            try:
                value = _parse_quantity(match.group("value"))
            except ValueError:
                continue
            matches.append((pattern_index, value))

    unique_values = sorted({value for _, value in matches})
    if not unique_values:
        return {
            "ok": False,
            "reason": "No unambiguous weekly capacity number found",
            "requires_confirmation": False,
            "raw_message": raw,
        }

    if len(unique_values) > 1:
        return {
            "ok": False,
            "reason": "Multiple possible capacity values found",
            "candidate_capacity_units": unique_values,
            "requires_confirmation": False,
            "raw_message": raw,
        }

    capacity = unique_values[0]
    strongest_pattern = min(index for index, value in matches if value == capacity)
    explicit_weekly_units = bool(
        re.search(
            r"(?i)\b(?:pairs|units|pieces|pcs)\s*(?:per|/)\s*week\b",
            raw,
        )
    )
    confidence = 0.99 if strongest_pattern == 0 and explicit_weekly_units else 0.95

    return {
        "ok": True,
        "capacity_units": capacity,
        "effective_until": _effective_until(raw),
        "parser_confidence": confidence,
        "requires_confirmation": True,
        "raw_message": raw,
    }
