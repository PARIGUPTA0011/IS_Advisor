"""RAG pipeline for IS-Advisor."""
import sys as _sys
from pathlib import Path as _Path

# `multilingual/` sits beside this package at the repo root and is shared with
# the semantic-search workstream. Importing it works out of the box when the
# process starts at the repo root (run_query.py, uvicorn api.main:app), and
# this keeps it working when it does not.
_REPO_ROOT = _Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))
