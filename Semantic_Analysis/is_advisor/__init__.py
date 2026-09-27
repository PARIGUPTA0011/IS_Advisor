"""IS-Advisor semantic search: procurement spec -> ranked Indian Standards."""
import sys as _sys
from pathlib import Path as _Path

# The multilingual layer (repo-root `multilingual/`) is shared with the RAG
# workstream, so it lives above this package rather than inside it. The scripts
# here run with Semantic_Analysis/ as sys.path[0], so the repo root is put on
# the path once, here, rather than in each entry point. This mirrors what
# rag/semantic_retriever.py already does in the opposite direction.
_REPO_ROOT = _Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

__all__ = [
    "config", "corpus", "documents", "gazetteer", "lexical", "dense",
    "query", "requirements", "rerank", "search",
]
