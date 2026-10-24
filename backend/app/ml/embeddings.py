"""Sentence embeddings with fastembed (BAAI/bge-small-en-v1.5, ONNX on CPU).

The model is loaded once and shared. When SKIP_MODEL_LOAD is set (tests, CI) no model is
loaded and callers fall back to lexical retrieval only.
"""

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedder:
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self.name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(list(texts))]


_lock = threading.Lock()
_embedder: Embedder | None = None
_load_failed = False


def get_embedder() -> Embedder | None:
    """Return the shared embedder, loading it on first use. None if unavailable."""
    global _embedder, _load_failed
    settings = get_settings()
    if settings.skip_model_load or _load_failed:
        return None
    with _lock:
        if _embedder is None:
            try:
                _embedder = FastEmbedder(settings.embedding_model)
            except Exception:
                log.exception("embedding model failed to load; dense retrieval disabled")
                _load_failed = True
                return None
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Override the shared embedder (used by tests)."""
    global _embedder
    _embedder = embedder


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / denom) if denom else 0.0
