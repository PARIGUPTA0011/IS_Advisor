"""
SINGLE SWAP POINT for the real semantic-search retriever.

This is the only file the retrieval teammate needs to touch to plug their
implementation into the RAG pipeline. Their retriever must satisfy
rag.retriever_interface.Retriever - a `.retrieve(query: str, top_k: int) ->
list[RetrievedEvidence]` method where each item has at least `kys_id` (int)
and `score` (float). Nothing else in this codebase depends on how those
results are produced (FAISS, Chroma, BM25, hybrid, ...).

Until the real retriever lands, MockRetriever (rag/mock_retriever.py) stands
in - a naive keyword-overlap scorer over real data, used only to validate
that the rest of the pipeline consumes retriever output correctly
(Checkpoints 2-8). It is NOT semantic search and should not be evaluated as
if it were.
"""

from rag.metadata_store import MetadataStore
from rag.retriever_interface import Retriever


def get_retriever(metadata_store: MetadataStore) -> Retriever:
    del metadata_store  # The semantic index owns its persisted corpus.
    from rag.semantic_retriever import SemanticRetriever

    return SemanticRetriever()
