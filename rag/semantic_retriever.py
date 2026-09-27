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
        from is_advisor import config
        from is_advisor.query import extract_is_numbers, strip_boilerplate
        from is_advisor.search import needs_multilingual_encoder

        # The same query cleaning the evaluation measures: re-split words PDF
        # extraction ran together, drop procurement boilerplate and quantities.
        # Cleaning removes citations, so any cited IS number is put back for
        # BM25 to match exactly - here it is the strongest signal a tender has.
        cleaned = " ".join([strip_boilerplate(query) or query, *extract_is_numbers(query)])
        candidates = self._retriever.retrieve(
            cleaned,
            top_k=top_k,
            use_reranker=self._use_reranker,
            use_bm25=True,
            use_dense=self._use_dense,
            # Text still in a non-Latin script (translation off or failed) goes
            # through the multilingual encoder, as in search_document().
            use_fallback_encoder=needs_multilingual_encoder(cleaned),
        )
        # A standard the query cites outright is a fact, not a guess: pin it
        # first, exactly as search_document() does, including the parts of a
        # cited number BIS has since split.
        pinned = []
        for cited in extract_is_numbers(query):
            citation = self._retriever.resolve_citation(cited)
            if citation.in_index:
                pinned.append(self._retriever._pin(cited, config.SCORE_CITED, f"cited explicitly as {cited}"))
            for part in citation.successor_parts:
                pinned.append(self._retriever._pin(part, config.SCORE_CITED_PART,
                                                   f"part of {cited}, which the query cites"))
        pinned_ids = {c.kys_id for c in pinned}
        candidates = (pinned + [c for c in candidates if c.kys_id not in pinned_ids])[:top_k]
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
