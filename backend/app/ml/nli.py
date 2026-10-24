"""Natural-language inference with a local CrossEncoder (premise = fact, hypothesis = claim).

The model is loaded once and shared. If it cannot load, `get_nli()` returns None and the
Claim Ledger falls back to exact numeric comparison plus lexical overlap at lower confidence.
"""

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)

NliScores = dict[str, float]  # {"entailment": p, "contradiction": p, "neutral": p}


class NliModel(Protocol):
    name: str

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]: ...


class CrossEncoderNli:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.name = model_name
        self._model = CrossEncoder(model_name, device="cpu")
        id2label = self._model.model.config.id2label
        self._labels = [id2label[i].lower() for i in range(len(id2label))]

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]:
        if not pairs:
            return []
        logits = np.asarray(self._model.predict(list(pairs), show_progress_bar=False))
        logits = logits - logits.max(axis=1, keepdims=True)
        probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
        return [{label: float(row[i]) for i, label in enumerate(self._labels)} for row in probs]


_lock = threading.Lock()
_nli: NliModel | None = None
_load_failed = False


def get_nli() -> NliModel | None:
    global _nli, _load_failed
    settings = get_settings()
    if settings.skip_model_load or _load_failed:
        return _nli
    with _lock:
        if _nli is None:
            try:
                _nli = CrossEncoderNli(settings.nli_model)
            except Exception:
                log.exception("NLI model failed to load; using numeric/lexical fallback")
                _load_failed = True
    return _nli


def set_nli(model: NliModel | None) -> None:
    """Override the shared NLI model (used by tests)."""
    global _nli
    _nli = model
