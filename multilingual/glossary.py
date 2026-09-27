"""Procurement trade terms in the language the officer types, not the one BIS writes.

This exists for the same reason `Semantic_Analysis/data/aliases.csv` exists,
one step further out. That file maps English procurement slang to standards
("TMT bar" -> IS 1786) and README section 7 measures it as the largest single
retrieval win available. But a translation model handed "सरिया" will produce
something like "rod" or "bar" - fluent, and not the trade term the keyword
index was built to match.

So glossary hits are appended to the translated query as English hints. Three
properties make this safe to do bluntly:

* **Additive.** A hit adds English terms and removes nothing, so a wrong row
  costs a little BM25 noise, never a lost match.
* **Deduplicated against the translation.** A hint the translation already
  produced is not appended twice, which would lengthen the document-side
  comparison for no gain (the same BM25 length penalty README section 7
  describes for long alias lists).
* **Matched on the original text**, before translation, because that is the
  only place the native-script term exists.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass

from . import config
from .detect import tokens_of

# A term shorter than this is matched only as a whole token. Substring matching
# is wrong here and produced a real false positive: "नल" (tap) occurs inside
# "स्टेनलेस" (stainless), because Indic scripts have no case or
# spacing cue to stop it, so "stainless steel water tank" picked up a hint for
# "tap water fitting". Longer terms may match a token prefix, which is what
# lets an inflected form ("टंकीयों") match its dictionary form ("टंकी").
_MIN_PREFIX_MATCH = 4


@dataclass(frozen=True)
class Entry:
    language: str
    term: str
    english: str


_ENTRIES: list[Entry] | None = None


def load(path=None) -> list[Entry]:
    """Read the glossary once and memoise it."""
    global _ENTRIES
    if _ENTRIES is not None and path is None:
        return _ENTRIES

    source = path or config.GLOSSARY_CSV
    entries: list[Entry] = []
    if source.exists():
        with open(source, encoding="utf-8", newline="") as handle:
            rows = (line for line in handle if not line.lstrip().startswith("#"))
            for row in csv.DictReader(rows):
                language = (row.get("lang") or "").strip()
                term = (row.get("term") or "").strip()
                english = (row.get("english") or "").strip()
                if language and term and english:
                    entries.append(Entry(language, term.lower(), english))
    # Longest term first, so "पानी की टंकी" wins over "पानी" when both are
    # present - the same longest-match rule the attribute gazetteers use.
    entries.sort(key=lambda entry: -len(entry.term))
    if path is None:
        _ENTRIES = entries
    return entries


def terms_for(language: str) -> list[Entry]:
    return [entry for entry in load() if entry.language == language]


def _matches(term: str, text_tokens: list[str], joined: str) -> bool:
    """Whether a glossary term is really present in the query.

    Multi-word terms are matched against the whitespace-joined token stream;
    single words against the tokens themselves, exactly for short terms and by
    prefix for longer ones.
    """
    if " " in term:
        return f" {term} " in joined
    for token in text_tokens:
        if token == term:
            return True
        if len(term) >= _MIN_PREFIX_MATCH and token.startswith(term):
            return True
    return False


def hints(text: str, language: str, already: str = "") -> list[str]:
    """English trade terms implied by `text`, minus anything `already` covers.

    `already` is the translated query: a term the translation produced is not
    worth repeating.
    """
    if not text or not language:
        return []
    text_tokens = [token.lower() for token in tokens_of(text)]
    joined = f" {' '.join(text_tokens)} "
    covered = set(re.findall(r"[a-z0-9]+", (already or "").lower()))
    found: list[str] = []
    for entry in terms_for(language):
        if not _matches(entry.term, text_tokens, joined):
            continue
        for word in entry.english.split():
            token = word.lower()
            if token not in covered and token not in found:
                found.append(word)
                covered.add(token)
    return found


def augment(query: str, original: str, language: str) -> str:
    """Append glossary hints for `original` to the translated `query`."""
    extra = hints(original, language, already=query)
    if not extra:
        return query
    return f"{query} {' '.join(extra)}".strip()
