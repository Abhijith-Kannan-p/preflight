"""Hybrid fact retrieval: dense (bge-small cosine) + BM25, fused with reciprocal rank fusion.

Current facts and superseded facts are searched as separate pools, so a claim that matches
an old fact can be recognised as outdated rather than simply unsupported.
"""

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.engine.context import FactInfo, ReviewContext
from app.ml.embeddings import Embedder, cosine

RRF_K = 60
TOP_K = 5
SUPERSEDED_K = 3

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "on",
    "in",
    "to",
    "for",
    "with",
    "by",
    "is",
    "are",
    "it",
    "its",
    "every",
    "all",
    "your",
    "you",
    "our",
    "we",
    "now",
    "that",
    "this",
    "at",
    "as",
    "be",
    "can",
    "from",
    "today",
    "paywise",
    "over",
    "under",
    "up",
    "than",
}


def _stem(token: str) -> str:
    return (
        token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token
    )


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


@dataclass(frozen=True)
class Candidate:
    fact: FactInfo
    rrf: float
    dense: float | None
    bm25: float


class FactIndex:
    def __init__(self, facts: list[FactInfo], embedder: Embedder | None) -> None:
        self.facts = facts
        self.embedder = embedder
        corpus = [tokens(f.statement) for f in facts]
        self._bm25 = BM25Okapi(corpus) if facts else None

    def search(self, query: str, k: int, query_vector: list[float] | None) -> list[Candidate]:
        if not self.facts or self._bm25 is None:
            return []
        bm25_scores = [float(s) for s in self._bm25.get_scores(tokens(query))]
        dense_scores: list[float | None] = [
            cosine(query_vector, f.embedding) if query_vector and f.embedding else None
            for f in self.facts
        ]
        rrf = [0.0] * len(self.facts)
        bm25_rank = sorted(range(len(self.facts)), key=lambda i: -bm25_scores[i])
        for rank, i in enumerate(bm25_rank):
            if bm25_scores[i] > 0:
                rrf[i] += 1 / (RRF_K + rank + 1)
        if any(d is not None for d in dense_scores):
            dense_rank = sorted(range(len(self.facts)), key=lambda i: -(dense_scores[i] or -1))
            for rank, i in enumerate(dense_rank):
                rrf[i] += 1 / (RRF_K + rank + 1)
        order = sorted(range(len(self.facts)), key=lambda i: -rrf[i])[:k]
        return [Candidate(self.facts[i], rrf[i], dense_scores[i], bm25_scores[i]) for i in order]


class Retriever:
    def __init__(self, ctx: ReviewContext, embedder: Embedder | None) -> None:
        self.embedder = embedder
        facts = list(ctx.facts.values())
        self.current = FactIndex([f for f in facts if f.current], embedder)
        self.superseded = FactIndex([f for f in facts if f.superseded_by], embedder)

    def retrieve(self, claim: str) -> tuple[list[Candidate], list[Candidate]]:
        vector = self.embedder.embed([claim])[0] if self.embedder else None
        return (
            self.current.search(claim, TOP_K, vector),
            self.superseded.search(claim, SUPERSEDED_K, vector),
        )
