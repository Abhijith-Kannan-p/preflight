"""Small text utilities shared by checkers: sentence spans and phrase search."""

import re
from collections.abc import Iterator
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\u2019-]*")


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


def sentences(text: str) -> list[TextSpan]:
    """Split text into sentence spans with exact offsets."""
    spans: list[TextSpan] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        if match.start() > start:
            spans.append(TextSpan(start, match.start(), text[start : match.start()]))
        start = match.end()
    if start < len(text):
        spans.append(TextSpan(start, len(text), text[start:]))
    return [s for s in spans if s.text.strip()]


def sentence_at(text: str, offset: int) -> TextSpan:
    for span in sentences(text):
        if span.start <= offset < span.end:
            return span
    return TextSpan(0, len(text), text)


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def phrase_pattern(phrase: str, case_sensitive: bool = False) -> re.Pattern[str]:
    """Match a phrase on word boundaries. Hyphenated compounds do not count as a match."""
    flags = 0 if case_sensitive else re.IGNORECASE
    escaped = re.escape(phrase)
    lead = r"(?<![\w-])" if phrase[:1].isalnum() else r"(?<!\w)"
    tail = r"(?![\w-])" if phrase[-1:].isalnum() else ""
    return re.compile(lead + escaped + tail, flags)


def find_phrase(text: str, phrase: str, case_sensitive: bool = False) -> Iterator[TextSpan]:
    for m in phrase_pattern(phrase, case_sensitive).finditer(text):
        yield TextSpan(m.start(), m.end(), m.group(0))


def compact(text: str) -> str:
    """Lowercase and drop everything except letters, digits and '&' (for presence checks)."""
    return re.sub(r"[^a-z0-9&]", "", text.lower())


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]
