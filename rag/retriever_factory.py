"""
SINGLE SWAP POINT for the real semantic-search retriever.

This is the only file the retrieval teammate needs to touch to plug their
implementation into the RAG pipeline. Their retriever must satisfy
rag.retriever_interface.Retriever - a `.retrieve(query: str, top_k: int) ->
list[RetrievedEvidence]` method where each item has at least `kys_id` (int)
and `score` (float). Nothing else in this codebase depends on how those
results are produced (FAISS, Chroma, BM25, hybrid, ...).

The swap has happened: this returns SemanticRetriever (rag/semantic_retriever.py),
which wraps the hybrid BM25 + dense retriever in Semantic_Analysis/.
MockRetriever (rag/mock_retriever.py) remains in the tree as the naive
keyword-overlap stand-in the pipeline was built against (Checkpoints 2-8), so
the checkpoint tests can still run without a built index. It is NOT semantic
search and should not be evaluated as if it were.

A non-English query never reaches here untranslated: rag/pipeline.py::run_query
translates it into English before retrieval, so this contract stays
English-only and the retriever sees exactly the text it was measured on.
"""

from rag.metadata_store import MetadataStore
from rag.retriever_interface import Retriever


def get_retriever(metadata_store: MetadataStore) -> Retriever:
    del metadata_store  # The semantic index owns its persisted corpus.
    from rag.semantic_retriever import SemanticRetriever

    return SemanticRetriever()
