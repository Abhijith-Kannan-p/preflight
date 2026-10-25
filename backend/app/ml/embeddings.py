"""Sentence embeddings with BAAI/bge-small-en-v1.5 (384-d), as a quantised ONNX model.

Uses the same quantised export fastembed ships (qdrant/bge-small-en-v1.5-onnx-q), run with a
lean ONNX Runtime session: CLS pooling and L2 normalisation, exactly as fastembed does for
bge models, so similarity thresholds calibrated earlier still hold.

The model is loaded once and shared. When SKIP_MODEL_LOAD is set (tests, CI) no model is
loaded and callers fall back to lexical retrieval only.
"""

import logging
import threading
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from app.config import get_settings
from app.ml.onnx import lean_session

log = logging.getLogger(__name__)
MAX_TOKENS = 256
BATCH = 16


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OnnxEmbedder:
    def __init__(self, model_name: str, onnx_repo: str, onnx_file: str) -> None:
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        self.name = model_name
        self.identity = f"{onnx_repo}/{onnx_file}"  # which exact weights produced the vectors
        self._tokenizer = Tokenizer.from_file(hf_hub_download(onnx_repo, "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding()
        self._session = lean_session(hf_hub_download(onnx_repo, onnx_file))
        self._inputs = {i.name for i in self._session.get_inputs()}

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH):
            encodings = self._tokenizer.encode_batch(list(texts[start : start + BATCH]))
            feed = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
            }
            hidden = self._session.run(None, {k: v for k, v in feed.items() if k in self._inputs})[
                0
            ]
            cls = hidden[:, 0]
            cls = cls / np.linalg.norm(cls, axis=1, keepdims=True).clip(min=1e-12)
            vectors += cls.astype(float).tolist()
        return vectors


_lock = threading.Lock()
_embedder: Embedder | None = None
_load_failed = False


def get_embedder() -> Embedder | None:
    """Return the shared embedder, loading it on first use. None if unavailable."""
    global _embedder, _load_failed
    settings = get_settings()
    if settings.skip_model_load or _load_failed:
        return _embedder
    with _lock:
        if _embedder is None:
            try:
                _embedder = OnnxEmbedder(
                    settings.embedding_model,
                    settings.embedding_onnx_repo,
                    settings.embedding_onnx_file,
                )
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
