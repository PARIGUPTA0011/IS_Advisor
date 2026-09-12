"""BM25 retrieval over the corpus.

Dense retrieval alone fails on two things that matter here: exact identifiers
("IS 1786") and near-identical titles separated only by a size or pattern name.
BM25 covers both, and fusing the two needs no training data.
"""
from __future__ import annotations

import pickle
import re

import numpy as np

from . import config

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Kept deliberately short. BM25 already discounts frequent terms, and words like
# "specification" do carry signal in this corpus.
_STOPWORDS = frozenset("""
a an the of for and or to in on at by with from as is are be been this that
these those its their it into over under per
""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


class BM25Index:
    """Thin wrapper so the retriever can be pickled and reloaded in one call."""

    def __init__(self, texts: list[str], kys_ids: list[int]):
        from rank_bm25 import BM25Okapi

        self.kys_ids = np.asarray(kys_ids)
        self._corpus_tokens = [tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(self._corpus_tokens)

    def search(self, query: str, top_k: int = config.BM25_TOP_K) -> list[tuple[int, float]]:
        """Return (row position, score) pairs, best first."""
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        if not np.any(scores):
            return []
        top_k = min(top_k, len(scores))
        top = np.argpartition(-scores, top_k - 1)[:top_k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]

    def save(self, path=config.BM25_PICKLE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def load(path=config.BM25_PICKLE) -> "BM25Index":
        with open(path, "rb") as fh:
            return pickle.load(fh)
