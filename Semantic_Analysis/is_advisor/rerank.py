"""Cross-encoder reranking of the fused candidate list.

The biggest single accuracy win available on documents this short, and cheap:
it only ever scores the top ~50 candidates for one line item, not the corpus.
"""
from __future__ import annotations

import numpy as np

from . import config

_cache: dict[str, object] = {}


def load_cross_encoder(name: str = config.CROSS_ENCODER):
    if name not in _cache:
        from sentence_transformers import CrossEncoder

        _cache[name] = CrossEncoder(name, device="cpu", max_length=256)
    return _cache[name]


def rerank(query: str, documents: list[str], model=None) -> np.ndarray:
    """Return a relevance score in 0..1 for each document, aligned to input order."""
    if not documents:
        return np.zeros(0, dtype="float32")
    model = model or load_cross_encoder()
    logits = np.asarray(model.predict([(query, d) for d in documents]), dtype="float32")
    return 1.0 / (1.0 + np.exp(-logits))  # ms-marco models emit raw logits
