"""Semantic drift of a suggestion: 1 - cosine(embed(original sentence), embed(revised sentence)).

Without the embedding model, a word-overlap distance is used and the label is the same.
"""

from difflib import SequenceMatcher
from typing import Literal

from app.engine.schema import Finding, NormalisedDoc
from app.engine.text import sentence_at, words
from app.ml.embeddings import Embedder, cosine

DriftLabel = Literal["low", "medium", "high"]


def drift_label(drift: float) -> DriftLabel:
    if drift < 0.15:
        return "low"
    return "medium" if drift < 0.35 else "high"


def revised_sentence(doc: NormalisedDoc, finding: Finding, replacement: str) -> tuple[str, str]:
    """Return (original sentence, sentence with the finding's span replaced)."""
    text = doc.blocks[finding.span.block].text
    sentence = sentence_at(text, finding.span.start)
    start = min(sentence.start, finding.span.start)
    end = max(sentence.end, finding.span.end)
    original = text[start:end]
    revised = (
        text[start : finding.span.start] + replacement + text[finding.span.end : end]
    ).strip()
    return original, revised


def _lexical_drift(a: str, b: str) -> float:
    return 1.0 - SequenceMatcher(None, words(a.lower()), words(b.lower())).ratio()


def compute_drift(original: str, revised: str, embedder: Embedder | None) -> float:
    if original.strip() == revised.strip():
        return 0.0
    if not revised.strip():
        return 1.0
    if embedder is None:
        return round(_lexical_drift(original, revised), 3)
    a, b = embedder.embed([original, revised])
    return round(max(0.0, 1.0 - cosine(a, b)), 3)


def attach_drift(doc: NormalisedDoc, findings: list[Finding], embedder: Embedder | None) -> None:
    for finding in findings:
        if finding.suggestion is None:
            continue
        original, revised = revised_sentence(doc, finding, finding.suggestion.text)
        finding.suggestion.drift = compute_drift(original, revised, embedder)
