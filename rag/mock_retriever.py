"""
MockRetriever - stands in for the teammate's semantic-search component.

This is NOT semantic search. It's a deliberately simple keyword-overlap
scorer over real titles from the dataset, used only to verify that the RAG
pipeline correctly consumes whatever a Retriever implementation produces
(per rag/retriever_interface.py). When the real retriever lands, it is a
drop-in replacement - the RAG code downstream never changes.

Because it's a real (if naive) scoring function over real data rather than
hardcoded answers, it also naturally produces "no evidence" for queries with
no vocabulary overlap and weak/noisy results for ambiguous queries - useful
for later checkpoints (weak/no-evidence handling), not just the happy path.
"""

import math
import re
from typing import Optional

from rag.metadata_store import MetadataStore
from rag.retriever_interface import RetrievedEvidence

_STOPWORDS = {
    "a", "an", "the", "for", "of", "and", "or", "to", "in", "on", "with",
    "is", "are", "be", "by", "at", "as", "this", "that", "part", "sec",
    "section", "specification", "general", "requirements",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


class MockRetriever:
    def __init__(self, metadata_store: MetadataStore):
        self._store = metadata_store
        self._index: list[tuple[int, str, set[str]]] = []
        for kys_id, record in metadata_store._by_id.items():
            tokens = set(_tokenize(record.title))
            if tokens:
                self._index.append((kys_id, record.title, tokens))

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedEvidence]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []

        scored: list[tuple[float, int, str]] = []
        for kys_id, title, title_tokens in self._index:
            overlap = query_tokens & title_tokens
            if not overlap:
                continue
            # simple cosine-like overlap score on unweighted bags of words
            score = len(overlap) / math.sqrt(len(query_tokens) * len(title_tokens))
            scored.append((score, kys_id, title))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[RetrievedEvidence] = []
        for score, kys_id, title in scored[:top_k]:
            record = self._store.get(kys_id)
            results.append(
                RetrievedEvidence(
                    kys_id=kys_id,
                    score=round(score, 4),
                    matched_text=title,
                    is_number=record.is_number if record else None,
                )
            )
        return results
