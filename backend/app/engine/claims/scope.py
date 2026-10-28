"""Scope and vagueness checks that run before a fact may judge a claim.

Scope: a fact about one payment method or app store says nothing about another.
"10% cashback on every UPI payment" is not contradicted by the PayWise Card's 1% cashback, and
"rated 4.8 on the Apple App Store" is not contradicted by the Google Play rating. When the claim
and the fact both name members of a scope group and share none, the fact is out of scope.
Products are not a scope group: they overlap (a PayWise Business merchant pays the fee on
PayWise Card transactions), so a product name alone does not make a fact irrelevant.

Vagueness: a claim with no number, no risky rule phrase and only hedged wording ("trusted by
millions", "popular with small businesses", "cheaper than most") cannot be checked against a
fact; it goes to a person ("needs a human look") instead of being called unsupported.
"""

import re

SCOPES: dict[str, dict[str, re.Pattern[str]]] = {
    "payment method": {
        "upi": re.compile(r"\bupi\b", re.I),
        "card": re.compile(r"\bcards?\b(?! is available)", re.I),
        "net_banking": re.compile(r"\bnet ?banking\b", re.I),
        "wallet": re.compile(r"\bwallets?\b", re.I),
    },
    "app store": {
        "google_play": re.compile(r"\bgoogle play\b|\bplay store\b|\bandroid\b", re.I),
        "apple": re.compile(r"\bapp store\b|\bapple\b|\bios\b|\biphone\b", re.I),
    },
}

_VAGUE = re.compile(
    r"\b(millions|thousands|lakhs|crores|countless|many|most|popular|popularity|growing|"
    r"fast-growing|almost|nearly|virtually|loved|favourite|favorite|everywhere|widely)\b"
    r"|\b(less|more|cheaper|better|faster|lower|higher)\b[\w\s]{0,20}\bthan (most|many|others?|"
    r"competitors|the rest)\b",
    re.I,
)
_NUMBER = re.compile(r"\d")


def _members(text: str, group: dict[str, re.Pattern[str]]) -> set[str]:
    return {name for name, pattern in group.items() if pattern.search(text)}


def out_of_scope(claim: str, fact: str) -> str | None:
    """The scope group in which claim and fact name different things, or None."""
    for group_name, group in SCOPES.items():
        in_claim, in_fact = _members(claim, group), _members(fact, group)
        if in_claim and in_fact and not in_claim & in_fact:
            return group_name
    return None


def is_vague(text: str) -> bool:
    """Hedged wording and no number to check."""
    return not _NUMBER.search(text) and _VAGUE.search(text) is not None
