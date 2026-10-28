"""Give freed memory back to the operating system on small hosts.

Python and ONNX Runtime free memory into glibc's heap, which keeps it; after dropping a model
or finishing a review, `malloc_trim(0)` returns the free pages, so resident memory falls back
instead of ratcheting up. A no-op where glibc is not available (macOS, Windows, musl).
"""

import ctypes
import ctypes.util
import gc
import logging

log = logging.getLogger(__name__)

_libc: ctypes.CDLL | None
try:
    _name = ctypes.util.find_library("c")
    _libc = ctypes.CDLL(_name) if _name else None
    if _libc is not None and not hasattr(_libc, "malloc_trim"):
        _libc = None
except OSError:
    _libc = None


def trim() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:  # pragma: no cover - platform specific
            log.debug("malloc_trim failed", exc_info=True)
