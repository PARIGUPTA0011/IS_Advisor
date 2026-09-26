"""Adapter from the semantic-analysis retriever to the RAG retriever contract."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from rag.retriever_interface import RetrievedEvidence


class SemanticRetriever:
    """Expose the hybrid semantic search through the RAG interface.

    The underlying retriever returns ``Candidate`` dataclasses and owns the
    BM25, dense, fusion, and optional reranking stages. RAG only needs the
    stable ``kys_id`` join key and a relative score, so this adapter keeps the
    two components decoupled.
    """

    def __init__(self, *, use_dense: bool = True, use_reranker: bool = False):
        semantic_root = Path(__file__).resolve().parent.parent / "Semantic_Analysis"
        if str(semantic_root) not in sys.path:
            sys.path.insert(0, str(semantic_root))

        from is_advisor.search import load_retriever

        self._use_dense = use_dense
        self._use_reranker = use_reranker
        self._retriever = load_retriever(
            with_dense=use_dense,
            with_reranker=use_reranker,
        )

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedEvidence]:
        candidates = self._retriever.retrieve(
            query,
            top_k=top_k,
            use_reranker=self._use_reranker,
            use_bm25=True,
            use_dense=self._use_dense,
        )
        return [self._to_evidence(candidate) for candidate in candidates]

    @staticmethod
    def _to_evidence(candidate: Any) -> RetrievedEvidence:
        return RetrievedEvidence(
            kys_id=int(candidate.kys_id),
            score=float(candidate.score),
            matched_text=candidate.title,
            is_number=candidate.is_number,
            why=candidate.why,
            tier=candidate.tier or None,
        )
