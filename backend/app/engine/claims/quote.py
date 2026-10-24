"""Quote check: a supported verdict must cite a verbatim span of the fact's text."""

import re

MIN_QUOTE_WORDS = 3


def _norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9%₹.-]+", text.lower().replace("\u2019", "'"))


def best_quote(claim: str, fact: str) -> str | None:
    """Longest run of consecutive words shared by claim and fact, returned as it appears in
    the fact text. None if the shared run is shorter than MIN_QUOTE_WORDS."""
    claim_words = [w.strip(".") for w in _norm_words(claim)]
    fact_tokens = list(re.finditer(r"\S+", fact))
    fact_words = [re.sub(r"[^a-z0-9%₹.-]", "", t.group(0).lower()).strip(".") for t in fact_tokens]
    best = (0, 0, 0)  # length, fact start index, fact end index
    for i in range(len(fact_words)):
        for j in range(len(claim_words)):
            length = 0
            while (
                i + length < len(fact_words)
                and j + length < len(claim_words)
                and fact_words[i + length]
                and fact_words[i + length] == claim_words[j + length]
            ):
                length += 1
            if length > best[0]:
                best = (length, i, i + length)
    if best[0] < MIN_QUOTE_WORDS:
        return None
    start = fact_tokens[best[1]].start()
    end = fact_tokens[best[2] - 1].end()
    return fact[start:end].rstrip(".,;")


def quote_is_verbatim(quote: str, fact: str) -> bool:
    return " ".join(quote.split()).lower() in " ".join(fact.split()).lower()
