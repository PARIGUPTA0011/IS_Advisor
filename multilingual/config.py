"""Settings for the multilingual layer. Every one of these is an env override.

Defaults are chosen for the same machine profile the rest of this repo targets:
CPU only, no API key, models downloaded once and then cached. Nothing here
reaches the network after the first run.

Sizes, so the disk cost is not a surprise:

| Model                                  | On disk |
|----------------------------------------|---------|
| `intfloat/multilingual-e5-small`       | ~470 MB |
| `ai4bharat/indictrans2-indic-en-dist-200M` | ~0.9 GB |
| `ai4bharat/indictrans2-en-indic-dist-200M` | ~0.9 GB |
| `facebook/nllb-200-distilled-600M`     | ~2.5 GB |

The IndicTrans2 pair is loaded only when an Indian language is actually seen,
and NLLB only when a non-Indian one is, so an English-only deployment
downloads neither.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_CSV = Path(__file__).resolve().parent / "data" / "glossary.csv"


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


# --- translation ------------------------------------------------------------

# Master switch. Off means detection and glossary still run, but no model is
# loaded and no text is translated - useful for measuring the retrieval side
# in isolation, and for a machine that cannot spare the disk.
TRANSLATION_ENABLED = _flag("IS_ADVISOR_TRANSLATE", True)

INDICTRANS2_INDIC_EN = os.getenv(
    "IS_ADVISOR_INDICTRANS2_INDIC_EN", "ai4bharat/indictrans2-indic-en-dist-200M"
)
INDICTRANS2_EN_INDIC = os.getenv(
    "IS_ADVISOR_INDICTRANS2_EN_INDIC", "ai4bharat/indictrans2-en-indic-dist-200M"
)
NLLB_MODEL = os.getenv("IS_ADVISOR_NLLB_MODEL", "facebook/nllb-200-distilled-600M")

# Greedy decoding by default. Beam search costs roughly one second per beam per
# line item on CPU, and a retrieval query does not need the fluency that buys -
# the words it recovers are the same. Raise it for the presentation direction
# if the prose reads badly.
NUM_BEAMS = _int("IS_ADVISOR_MT_BEAMS", 1)
MAX_NEW_TOKENS = _int("IS_ADVISOR_MT_MAX_TOKENS", 256)
BATCH_SIZE = _int("IS_ADVISOR_MT_BATCH", 8)
DEVICE = os.getenv("IS_ADVISOR_MT_DEVICE", "cpu")

# Translated strings are cached in-process, keyed by (text, source, target).
# Field labels, tier names and warnings repeat on every request, so this saves
# most of the presentation-side cost after the first query.
CACHE_SIZE = _int("IS_ADVISOR_MT_CACHE", 4096)

# --- output ----------------------------------------------------------------

# Official IS numbers and titles are never translated: the number is an
# identifier and the title is the standard's legal name. A translated gloss is
# offered alongside them instead, and this switch turns that gloss off.
TRANSLATE_TITLES = _flag("IS_ADVISOR_TRANSLATE_TITLES", True)
