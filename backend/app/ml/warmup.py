"""Load and warm up local models once at startup, in a background thread.

/health reports `models_ready` so the frontend can show "Waking up the engine..." until then.
"""

import logging
import threading
import time
from collections.abc import Callable

from app.ml.embeddings import get_embedder
from app.ml.nli import get_nli

log = logging.getLogger(__name__)

_ready = threading.Event()
_status: dict[str, str | float | None] = {"embedder": None, "nli": None, "seconds": None}


def _warm(after: Callable[[], None] | None = None) -> None:
    started = time.perf_counter()
    try:
        embedder = get_embedder()
        if embedder:
            embedder.embed(["PayWise settles merchant payments quickly."])
        _status["embedder"] = embedder.name if embedder else None
        nli = get_nli()
        if nli:
            nli.predict([("PayWise is regulated.", "PayWise is regulated.")])
        _status["nli"] = nli.name if nli else None
    except Exception:
        log.exception("model warm-up failed; engine continues in fallback mode")
    finally:
        _status["seconds"] = round(time.perf_counter() - started, 1)
        _ready.set()
        log.info("models warm: %s", _status)
    if after is not None:
        try:
            after()
        except Exception:
            log.exception("post-warm-up task failed")


def start_warmup(after: Callable[[], None] | None = None) -> None:
    threading.Thread(target=_warm, args=(after,), name="model-warmup", daemon=True).start()


def models_ready() -> bool:
    return _ready.is_set()


def model_status() -> dict[str, str | float | None]:
    return dict(_status)
