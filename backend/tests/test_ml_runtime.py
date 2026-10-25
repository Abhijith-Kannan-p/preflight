"""Small-host ML runtime: tokenizer truncation, load-failure fallback, re-embedding."""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.engine.claims.ledger import ClaimLedger
from app.engine.normalise import from_text
from app.ml import nli
from app.ml.nli import PairTokenizer
from app.models import Fact, Workspace
from app.seed import WORKSPACE_ID, ensure_fact_embeddings
from tests.engine_helpers import LINKEDIN_SAMPLE, context
from tests.fakes import HashingEmbedder


class FakeSentencePiece:
    """One id per character, so lengths are easy to reason about."""

    def encode(self, text: str) -> list[int]:
        return [10 + (ord(c) % 50) for c in text]


def _tokenizer() -> PairTokenizer:
    tok = PairTokenizer.__new__(PairTokenizer)
    tok._sp = FakeSentencePiece()
    return tok


def test_pair_encoding_layout_and_padding() -> None:
    feed = _tokenizer().encode_batch([("ab", "c"), ("abcd", "ef")])
    first, second = feed["input_ids"].tolist()
    assert first[:5] == [PairTokenizer.CLS, *first[1:3], PairTokenizer.SEP, first[4]]
    assert first[-1] == PairTokenizer.PAD and second[-1] == PairTokenizer.SEP
    assert feed["attention_mask"].tolist() == [[1] * 6 + [0] * 3, [1] * 9]
    assert feed["token_type_ids"].tolist()[1] == [0] * 6 + [1] * 3


def test_long_pairs_are_truncated_longest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nli, "MAX_TOKENS", 10)
    ids = _tokenizer().encode_batch([("a" * 20, "b" * 3)])["input_ids"].tolist()[0]
    assert len(ids) == 10  # 3 special tokens + 7 content tokens
    assert ids.count(10 + ord("b") % 50) == 3  # the short hypothesis survives intact


def test_nli_load_failure_falls_back_to_lexical(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> None:
        raise OSError("model file missing")

    monkeypatch.setattr(get_settings(), "skip_model_load", False)
    monkeypatch.setattr(nli, "OnnxNli", broken)
    monkeypatch.setattr(nli, "_nli", None)
    monkeypatch.setattr(nli, "_load_failed", False)
    assert nli.get_nli() is None
    ledger = ClaimLedger(nli.get_nli(), embedder=None)
    findings = asyncio.run(ledger.run(from_text(LINKEDIN_SAMPLE), context(session)))
    assert "CLM-04" in {f.rule.id for f in findings}  # deterministic checks still work
    assert any("lexical fallback" in step for r in ledger.records for step in r.steps)


class RenamedEmbedder(HashingEmbedder):
    identity = "another-model/model.onnx"

    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[0.0] * 383 + [1.0] for _ in texts]


def test_facts_are_reembedded_when_the_embedding_model_changes(session: Session) -> None:
    assert ensure_fact_embeddings(session, WORKSPACE_ID, HashingEmbedder()) == 0  # unchanged
    changed = ensure_fact_embeddings(session, WORKSPACE_ID, RenamedEmbedder())
    total = len(session.scalars(select(Fact.id)).all())
    assert changed == total
    fact = session.get_one(Fact, "F-087")
    assert fact.embedding is not None and float(fact.embedding[-1]) == 1.0
    settings = session.get_one(Workspace, WORKSPACE_ID).settings
    assert settings["embedding_identity"] == "another-model/model.onnx"
    assert ensure_fact_embeddings(session, WORKSPACE_ID, RenamedEmbedder()) == 0
