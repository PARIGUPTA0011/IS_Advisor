"""Split words that PDF extraction ran together.

A third of real tender lines come out of pdfplumber with the spaces gone -
"Supplying,installing,testingandcommissioningofGIpipes" - and those lines
scored 0.464 Recall@5 against 0.638 for the rest (README section 7). Neither
retriever can match "testingandcommissioningofgipipes".

The fix is a word segmentation pass: dynamic programming over each long run
of letters, choosing the split whose words are most frequent. Frequencies come
from our own corpus (titles, classification path, clause 1 scope text), so the
vocabulary is BIS's own, plus a short list of procurement verbs the standards
never use. No model, no download.

It is conservative on purpose. A run is only rewritten when it is long, is not
itself a known word, and splits entirely into known words. Anything else is
left exactly as it was, so a clean line passes through unchanged.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from . import config

MIN_RUN = 8           # shorter runs are left alone: "gi", "xlpe", "hdpe" are real tokens
MAX_WORD = 20         # longest single word the splitter will propose
MIN_PIECE = 2         # never split off a one-letter word except "a"
MIN_AVG_PIECE = 4.0   # mean letters per piece; below it the "split" is a misspelling

# Procurement wording that BIS titles and scopes rarely use, so the corpus
# alone would not know them. Generic verbs only - nothing specific to a product.
_PROCUREMENT_WORDS = """
providing supplying supply installing installation testing commissioning fixing laying jointing
erecting erection fabricating fabrication dismantling including complete completed approved make
required requirement contractor engineer charge direction directed site work works per necessary
specification specifications materials labour cost all with without and the of to in on for by at
as or etc nos each set lot inside outside wall walls ceiling floor floors grade class type size sizes
""".split()

# Pieces of three letters or fewer must come from this list. The corpus alone
# cannot be trusted for them: OCR'd scope text is full of fragments ("ent",
# "ion", "tur") as frequent as real words ("tee", "pvc"), and allowing them
# split misspellings like "treatement" into "treat em ent" - which measurably
# cost recall on clean lines. Function words plus the abbreviations tenders use.
_SHORT_WORDS = frozenset("""
a an of to in on at by or as is it be no up and the for per all any its are
gi ms ci di cp pvc tmt rcc pcc led mcb sdr abc upvc hd ld pe pp ss ht lt kv ac dc ip ss
tee cap rod nut box fan bar gun set top way hot bed dia new old air oil gas
fe mm cm kg sq kw hp rm nos
""".split())

_RUN_RE = re.compile(r"[A-Za-z]+")


@lru_cache(maxsize=1)
def _costs() -> dict[str, float]:
    """Zipf-style cost per known word: frequent words are cheap."""
    counts: Counter[str] = Counter()
    try:
        import pandas as pd

        corpus = pd.read_parquet(config.CORPUS_PARQUET, columns=["doc_text", "lexical_text"])
        for text in corpus["doc_text"].tolist() + corpus["lexical_text"].tolist():
            counts.update(w for w in _RUN_RE.findall(text.lower()) if len(w) <= MAX_WORD)
    except Exception:
        return {}          # no built corpus: the splitter becomes a no-op
    for word in _PROCUREMENT_WORDS:
        counts[word] += max(counts.values(), default=1)
    # Drop one-letter noise except "a"; OCR leaves stray letters in scope text.
    words = [w for w, _ in counts.most_common() if len(w) >= MIN_PIECE or w == "a"]
    log_n = math.log(len(words))
    return {w: math.log((rank + 1) * log_n) for rank, w in enumerate(words)}


def _split_run(run: str) -> list[str] | None:
    """Best split of one lowercase run into known words, or None."""
    costs = _costs()
    n = len(run)
    best = [0.0] + [math.inf] * n
    back = [0] * (n + 1)
    for end in range(1, n + 1):
        for start in range(max(0, end - MAX_WORD), end):
            piece = run[start:end]
            if len(piece) <= 3 and piece not in _SHORT_WORDS:
                continue
            word_cost = costs.get(piece)
            if word_cost is not None and best[start] + word_cost < best[end]:
                best[end] = best[start] + word_cost
                back[end] = start
    if math.isinf(best[n]):
        return None
    words, end = [], n
    while end > 0:
        words.append(run[back[end]:end])
        end = back[end]
    return words[::-1]


def split_run_together(text: str) -> str:
    """Re-insert spaces in long letter runs that are not words themselves."""
    costs = _costs()
    if not costs:
        return text

    def fix(match: re.Match) -> str:
        run = match.group(0)
        lower = run.lower()
        if len(run) < MIN_RUN or lower in costs:
            return run
        words = _split_run(lower)
        # A misspelling that happens to split ("construcion" -> "constru ci on")
        # shatters into short pieces; genuinely glued text averages ~5 letters.
        if not words or len(words) < 2 or len(lower) / len(words) < MIN_AVG_PIECE:
            return run
        return " ".join(words)

    # Commas and ampersands glued between words ("Supplying,installing") are
    # separators too; give them a space so the runs on either side are seen.
    text = re.sub(r"(?<=[A-Za-z])([,&])(?=[A-Za-z])", r"\1 ", text)
    return _RUN_RE.sub(fix, text)
