"""
Contract between the semantic-search/retrieval component (teammate's work)
and the RAG pipeline (this package).

The RAG layer must never depend on how retrieval is implemented (FAISS,
Chroma, BM25, hybrid, ...). It only depends on this module.

Only `kys_id` and `score` are load-bearing. Everything else is optional,
best-effort context for traceability/debugging and is never required for
grounding decisions later in the pipeline.
"""

from typing import Optional, Protocol, TypedDict


class RetrievedEvidence(TypedDict, total=False):
    kys_id: int                    # REQUIRED. Primary key into standards.csv/jsonl and the KG.
    score: float                   # REQUIRED. Relevance score, any scale, treated as opaque/relative.
    matched_text: Optional[str]    # OPTIONAL. Snippet/title the retriever matched on.
    is_number: Optional[str]       # OPTIONAL. Convenience only; RAG re-hydrates the authoritative value.


REQUIRED_FIELDS = ("kys_id", "score")


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedEvidence]:
        """Return up to top_k RetrievedEvidence entries for the query, ranked by relevance."""
        ...


def validate_retrieved_evidence(items: list[RetrievedEvidence]) -> None:
    """Fail loudly if a retriever implementation violates the minimum contract."""
    for i, item in enumerate(items):
        for field in REQUIRED_FIELDS:
            if field not in item or item[field] is None:
                raise ValueError(
                    f"RetrievedEvidence[{i}] is missing required field '{field}': {item}"
                )
        if not isinstance(item["kys_id"], int):
            raise ValueError(
                f"RetrievedEvidence[{i}].kys_id must be int, got {type(item['kys_id'])}: {item}"
            )
