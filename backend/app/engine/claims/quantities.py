"""Exact numeric comparison: extract quantities with units from claims and facts.

A quantity is (family, value, span). Values are normalised within a family (time in seconds,
counts in units, fees in percent) so "under 5 seconds" and "under 10 seconds" compare as
5 vs 10. A mismatch on the same topic makes a claim contradicted regardless of the NLI model.
"""

import re
from dataclasses import dataclass

from app.engine.text import TextSpan

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30,
}  # fmt: skip
_MULTIPLIERS = {"thousand": 1e3, "k": 1e3, "lakh": 1e5, "million": 1e6, "crore": 1e7,
                "billion": 1e9}  # fmt: skip
_TIME = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "day": 86400,
         "week": 604800, "month": 2592000, "year": 31536000}  # fmt: skip
_FEE_WORDS = re.compile(r"\b(fees?|charges?|mdr|merchant discount rate|commission)\b", re.I)

_QUALIFIER = (
    r"(?:\b(?:under|over|up to|more than|less than|within|at least|nearly|about|only|just)\s+)?"
)
# A number on its own: not part of "AES-256", "#1", "24x7" or a word like "milestone".
_NUM = r"(?<![\w#.-])(?:\d+(?:[.,]\d+)*|(?:" + "|".join(_NUMBER_WORDS) + r")\b)(?![\w-]*\d)(?!x\d)"
_QUANTITY = re.compile(
    _QUALIFIER
    + r"(?P<currency>₹|rs\.?\s?)?(?P<num>"
    + _NUM
    + r")\s?(?P<mult>thousand|lakh|million|crore|billion|k\b)?\s?"
    + r"(?P<unit>%|percent\b|seconds?\b|secs?\b|minutes?\b|mins?\b|hours?\b|days?\b|weeks?\b|"
    + r"months?\b|years?\b)?"
    + r"(?P<rating>\s?(?:out of|/)\s?5)?",
    re.IGNORECASE,
)
_NEXT_WORDS = re.compile(r"\s*([A-Za-z-]+)(?:\s+([A-Za-z-]+))?")
_COUNT_ADJECTIVES = {"registered", "active", "new", "more", "indian", "happy", "different",
                     "unique", "monthly", "daily", "of"}  # fmt: skip
_ZERO_FEE = re.compile(
    r"\b(?:zero|no|nil)\s+(?:[a-z]+\s+){0,2}?(?:fees?|charges?|mdr|merchant discount rate|"
    r"commission)\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^(19|20)\d\d$")


@dataclass(frozen=True)
class Quantity:
    family: str
    value: float
    span: TextSpan


def _to_number(raw: str) -> float:
    lowered = raw.lower()
    if lowered in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[lowered])
    return float(raw.replace(",", ""))


def _counted_noun(text: str, end: int) -> str:
    """What a bare count counts ("12 million registered users" -> "user"), so counts of
    different things are never compared."""
    m = _NEXT_WORDS.match(text, end)
    if m is None:
        return ""
    for word in (w for w in m.groups() if w):
        word = word.lower()
        if word not in _COUNT_ADJECTIVES and "-" not in word:
            return word[:-1] if word.endswith("s") and len(word) > 3 else word
    return ""


def extract(text: str) -> list[Quantity]:
    found: list[Quantity] = []
    taken: list[tuple[int, int]] = []
    for m in _ZERO_FEE.finditer(text):
        found.append(Quantity("fee", 0.0, TextSpan(m.start(), m.end(), m.group(0))))
        taken.append((m.start(), m.end()))
    fee_context = bool(_FEE_WORDS.search(text))
    for m in _QUANTITY.finditer(text):
        if any(a <= m.start("num") < b for a, b in taken):
            continue
        num, unit = m.group("num"), (m.group("unit") or "").lower()
        if _YEAR.match(num) and not unit:
            continue  # years are dates, not quantities
        value = _to_number(num)
        if m.group("mult"):
            value *= _MULTIPLIERS[m.group("mult").lower()]
        if m.group("rating"):
            family = "rating"
        elif m.group("currency"):
            family = "currency"
        elif unit in ("%", "percent"):
            family = "fee" if fee_context else "percent"
        elif unit:
            key = unit.rstrip("s")
            family, value = "time", value * _TIME.get(key, _TIME.get(key[:3], 1))
        else:
            family = f"count:{_counted_noun(text, m.end())}"
        span = m.group(0).rstrip()
        found.append(Quantity(family, value, TextSpan(m.start(), m.start() + len(span), span)))
    return found


def compare(claim: str, fact: str) -> tuple[str, Quantity | None, Quantity | None]:
    """Return ("match" | "mismatch" | "na", claim quantity, fact quantity) for one pair."""
    claim_qs, fact_qs = extract(claim), extract(fact)
    for cq in claim_qs:
        same_family = [fq for fq in fact_qs if fq.family == cq.family]
        if not same_family:
            continue
        if any(abs(fq.value - cq.value) < 1e-9 for fq in same_family):
            match = next(fq for fq in same_family if abs(fq.value - cq.value) < 1e-9)
            return "match", cq, match
        return "mismatch", cq, same_family[0]
    return "na", None, None
