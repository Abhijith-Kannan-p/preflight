"""Mask confidential data before any external LLM call, and restore it afterwards.

Confidential terms from the Brand Knowledge Base, emails, phone numbers and ₹ amounts are
replaced with stable tokens such as [CONFIDENTIAL_1] and [PRICE_1]. The same value always
gets the same token within one Masker, so the model can still reason about repetition.
"""

import re
from dataclasses import dataclass, field

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\w)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")
_PRICE = re.compile(r"(?:₹|Rs\.?\s?|INR\s?)\d[\d,]*(?:\.\d+)?(?:\s?/\s?(?:month|year|mo|yr))?")
_TOKEN = re.compile(r"\[(CONFIDENTIAL|EMAIL|PHONE|PRICE)_\d+\]")


@dataclass
class Masker:
    confidential_terms: tuple[str, ...] = ()
    enabled: bool = True
    _forward: dict[str, str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    @property
    def masked_count(self) -> int:
        return len(self._forward)

    def _token(self, kind: str, value: str) -> str:
        if value not in self._forward:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            token = f"[{kind}_{self._counts[kind]}]"
            self._forward[value] = token
            self._reverse[token] = value
        return self._forward[value]

    def mask(self, text: str) -> str:
        if not self.enabled:
            return text
        # Longest confidential terms first, so "PayWise Gold" wins over a shorter overlap.
        for term in sorted(self.confidential_terms, key=len, reverse=True):
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            text = pattern.sub(lambda m: self._token("CONFIDENTIAL", m.group(0)), text)
        text = _PRICE.sub(lambda m: self._token("PRICE", m.group(0)), text)
        text = _EMAIL.sub(lambda m: self._token("EMAIL", m.group(0)), text)
        return _PHONE.sub(lambda m: self._token("PHONE", m.group(0)), text)

    def unmask(self, text: str) -> str:
        return _TOKEN.sub(lambda m: self._reverse.get(m.group(0), m.group(0)), text)
