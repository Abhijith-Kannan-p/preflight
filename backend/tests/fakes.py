"""Deterministic stand-ins for ML models so tests run fast and offline."""

import hashlib
import math
import re
from collections.abc import Sequence

from app.models import EMBEDDING_DIM


class HashingEmbedder:
    """Bag-of-words hashed into a fixed-size vector. Similar wording -> similar vectors."""

    name = "test-hashing-embedder"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % EMBEDDING_DIM
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
