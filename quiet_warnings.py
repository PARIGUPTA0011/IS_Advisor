"""Silence third-party warnings that this project cannot act on.

Two warnings turn up on every run that touches the model stack, neither of
which says anything about this code:

* `FutureWarning: clean_up_tokenization_spaces was not set` - transformers
  announcing a default change in its own tokenizer API. The value is not set
  by this project and nothing here depends on it.
* `UserWarning: TypedStorage is deprecated` - torch, raised while loading a
  checkpoint. It is about torch's storage classes, which this project never
  touches directly.

Together they bury the output of `run_query.py`, and a warning nobody can act
on trains people to ignore warnings that matter - which is the real cost.

**Called from entry points only.** Applications get to set a warnings policy;
libraries do not, because a library that mutates the global filter takes the
decision away from whatever imports it. So this is invoked from `run_query.py`,
`api/main.py` and `Semantic_Analysis/03_search.py`, and never from a module
that only gets imported.

Both filters are narrow: matched on message text and category, so a *new*
warning from either library still gets through. `PYTHONWARNINGS=default` or
`IS_ADVISOR_ALL_WARNINGS=1` turns them back on.
"""

from __future__ import annotations

import os
import warnings

# (message regex, category) - narrow on purpose. A filter on the whole module
# would also hide the next warning transformers or torch adds, which may be one
# worth reading.
_SUPPRESSED: tuple[tuple[str, type[Warning]], ...] = (
    ("`clean_up_tokenization_spaces` was not set", FutureWarning),
    ("TypedStorage is deprecated", UserWarning),
)

_applied = False


def apply() -> bool:
    """Install the filters. Returns False if disabled or already applied."""
    global _applied
    if _applied:
        return False
    if (os.getenv("IS_ADVISOR_ALL_WARNINGS", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    for message, category in _SUPPRESSED:
        warnings.filterwarnings("ignore", message=message, category=category)
    _applied = True
    return True


def suppressed() -> list[str]:
    """What `apply()` hides, for a docstring or a `--help` note to quote."""
    return [f"{category.__name__}: {message}" for message, category in _SUPPRESSED]
