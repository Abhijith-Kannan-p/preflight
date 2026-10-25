"""Natural-language inference with a local cross-encoder (premise = fact, hypothesis = claim).

Two interchangeable backends:
- "onnx" (default): the model's official int8-quantised ONNX export run with ONNX Runtime and
  the Rust `tokenizers` library. No PyTorch, about 90 MB on disk; fits small hosts (512 MB).
- "torch": the same model through sentence-transformers (needs requirements-ml.txt).

The model is loaded once, on first use or at warm-up. If it cannot load, `get_nli()` returns
None and the Claim Ledger falls back to exact numeric comparison plus lexical overlap.
"""

import json
import logging
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from app.config import get_settings
from app.ml.onnx import lean_session

log = logging.getLogger(__name__)

NliScores = dict[str, float]  # {"entailment": p, "contradiction": p, "neutral": p}
_inference_lock = threading.Lock()
MAX_TOKENS = 256


class NliModel(Protocol):
    name: str

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]: ...


def _softmax_rows(logits: Any, labels: list[str]) -> list[NliScores]:
    logits = np.asarray(logits, dtype=np.float64)
    logits = logits - logits.max(axis=1, keepdims=True)
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    return [{label: float(row[i]) for i, label in enumerate(labels)} for row in probs]


class PairTokenizer:
    """DeBERTa-v3 pair encoding ([CLS] a [SEP] b [SEP]) with SentencePiece.

    Gives the same ids as the model's tokenizer.json (checked on test pairs) in half the
    memory: the 128k-entry unigram vocabulary costs about 56 MiB here vs 106 MiB through
    the `tokenizers` library, which matters on a 512 MB host.
    """

    CLS, SEP, PAD = 1, 2, 0

    def __init__(self, spm_path: str) -> None:
        import sentencepiece as spm

        self._sp = spm.SentencePieceProcessor(model_file=spm_path)

    def encode_batch(self, pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
        rows: list[tuple[list[int], list[int]]] = []
        for premise, hypothesis in pairs:
            a, b = self._sp.encode(premise), self._sp.encode(hypothesis)
            while len(a) + len(b) > MAX_TOKENS - 3:  # longest-first truncation
                (a if len(a) >= len(b) else b).pop()
            ids = [self.CLS, *a, self.SEP, *b, self.SEP]
            types = [0] * (len(a) + 2) + [1] * (len(b) + 1)
            rows.append((ids, types))
        width = max(len(ids) for ids, _ in rows)
        pad = [width - len(ids) for ids, _ in rows]
        return {
            "input_ids": np.array(
                [ids + [self.PAD] * p for (ids, _), p in zip(rows, pad, strict=True)],
                dtype=np.int64,
            ),
            "attention_mask": np.array(
                [[1] * len(ids) + [0] * p for (ids, _), p in zip(rows, pad, strict=True)],
                dtype=np.int64,
            ),
            "token_type_ids": np.array(
                [types + [0] * p for (_, types), p in zip(rows, pad, strict=True)], dtype=np.int64
            ),
        }


class OnnxNli:
    def __init__(self, model_name: str, onnx_file: str) -> None:
        from huggingface_hub import hf_hub_download

        self.name = f"{model_name} (ONNX int8)"
        model_path = hf_hub_download(model_name, onnx_file)
        config = json.loads(Path(hf_hub_download(model_name, "config.json")).read_text())
        self._labels = [config["id2label"][str(i)].lower() for i in range(len(config["id2label"]))]
        self._tokenizer = PairTokenizer(hf_hub_download(model_name, "spm.model"))
        self._session = lean_session(model_path)
        self._inputs = {i.name for i in self._session.get_inputs()}

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]:
        # DeBERTa's relative attention needs about 20 MiB per pair in flight, so small hosts
        # use small batches (NLI_BATCH_SIZE), and one inference runs at a time.
        batch = get_settings().nli_batch_size
        scores: list[NliScores] = []
        with _inference_lock:
            for start in range(0, len(pairs), batch):
                scores += self._predict_batch(pairs[start : start + batch])
        return scores

    def _predict_batch(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]:
        feed = self._tokenizer.encode_batch(pairs)
        inputs = {k: v for k, v in feed.items() if k in self._inputs}
        return _softmax_rows(self._session.run(None, inputs)[0], self._labels)


class TorchNli:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.name = model_name
        self._model = CrossEncoder(model_name, device="cpu")
        id2label = self._model.model.config.id2label
        self._labels = [id2label[i].lower() for i in range(len(id2label))]

    def predict(self, pairs: Sequence[tuple[str, str]]) -> list[NliScores]:
        if not pairs:
            return []
        logits = self._model.predict(list(pairs), show_progress_bar=False)
        return _softmax_rows(logits, self._labels)


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
                _nli = (
                    OnnxNli(settings.nli_model, settings.nli_onnx_file)
                    if settings.nli_backend == "onnx"
                    else TorchNli(settings.nli_model)
                )
            except Exception:
                log.exception("NLI model failed to load; using numeric/lexical fallback")
                _load_failed = True
    return _nli


def set_nli(model: NliModel | None) -> None:
    """Override the shared NLI model (used by tests)."""
    global _nli
    _nli = model
