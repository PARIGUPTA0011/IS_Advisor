"""Keeping the load-bearing tokens intact across a translation.

A procurement query is mostly technical notation, and the notation is the part
that decides the answer: `IS 1786`, `Fe500D`, `IP66`, `DN 150`, `90W`, `K9`.
Machine translation is free to reword prose, but it must not touch any of
that - an `IS 1786` that comes back as `IS 1,786` stops matching the citation
regex in `Semantic_Analysis/is_advisor/query.py`, and a `Fe500D` that comes
back as `Fe500 D` stops matching the index.

Two strategies, because the two directions have different needs:

* **Into English** (the retrieval direction) - `lift()` pulls the technical
  spans out, the prose is translated without them, and they are appended to
  the English result. The query is a bag of terms by the time BM25 and the
  bi-encoder see it, so position does not matter, and nothing can come back
  mangled because nothing was ever handed to the model.
* **Out of English** (the presentation direction) - `mask()` substitutes
  placeholders, because a human reads this text and word order matters.
  `unmask()` reports what it could not put back, so a caller can fall back to
  the English sentence rather than show a sentence with a hole in it.

Placeholders are `@1@`, `@2@`, ... and that shape was **measured, not guessed**.
The first version used letters only (`PLHA`, `PLHB`) on the theory that digits
are what a translation model reformats between locales. Letters turned out to be
worse: NLLB-200 *transliterates* them, so `PLHA` came back as `पीलहेऐ`
in Hindi and `பிஎல்ஹே` in Tamil, and the IS number it stood for
fell out of the middle of the sentence. Testing nine candidate shapes through
the real model showed that punctuation-delimited numerals (`@1@`, `<1>`, `{1}`,
`(1)`) survive in both languages while letter forms do not.

`@1@` is the pick. `[1]` survives equally well but is exactly the evidence-tag
notation the RAG context builder already uses (`rag/context_builder.py`), so a
placeholder in that shape could collide with real content in an LLM's `reason`
text. The digit inside can still be re-rendered in the target script's numerals,
so `unmask` matches every Unicode spelling of it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .detect import digit_variants

# Order matters: the first pattern that claims a span owns it. IS citations
# come first so that "IS 1786" is never split into "IS" plus a bare number.
_PROTECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # IS citations in every spelling the query layer already handles.
    ("citation", re.compile(
        r"\bIS(?:\s*/\s*(?:ISO|IEC|TS|TR|QC|EN))*\s*[:.]?\s*\d{1,5}"
        r"(?:\s*\(?\s*Part\s*\d+\s*(?:/\s*Sec(?:tion)?\s*\d+\s*)?\)?)?"
        r"(?:\s*\(?\s*Sec(?:tion)?\s*\d+\s*\)?)?"
        r"(?:\s*[:\-]\s*(?:19|20)\d{2})?",
        re.IGNORECASE)),
    # Other standards bodies a tender cites alongside IS.
    ("citation", re.compile(r"\b(?:ISO|IEC|EN|ASTM|BS|DIN|JIS)\s*[:\-]?\s*\d{2,6}(?:[:\-]\d{4})?\b",
                            re.IGNORECASE)),
    # Grade and class codes: Fe500D, M25, K9, PE100, IP66, SS304, B-class.
    ("code", re.compile(r"\b(?:Fe|M|K|PE|IP|SS|MS|GI|DI|CI|HDPE|UPVC|PVC|NP|FRLS|XLPE)\s?-?\s?\d{1,4}[A-Za-z]{0,2}\b")),
    # Unit-first notation: DN 150, NB 25, PN 16.
    ("code", re.compile(r"\b(?:DN|NB|PN|AWG|SWG)\s?\d{1,4}\b", re.IGNORECASE)),
    # A number with a unit attached, the form requirement extraction reads.
    ("quantity", re.compile(
        r"\b\d+(?:[.,]\d+)?\s?(?:mm|cm|m|km|kg|g|mg|t|mt|ton(?:ne)?s?|l|ltr?s?|ml|"
        r"sqm|cum|m2|m3|kw|kva|kv|v|w|hp|a|amp(?:ere)?s?|hz|bar|psi|deg|nos|pcs)\b",
        re.IGNORECASE)),
    # Anything left that is letters and digits welded together is notation.
    ("code", re.compile(r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{2,12}\b")),
    # Bare numbers last, so every richer form above has already claimed its own.
    ("number", re.compile(r"\b\d+(?:[.,]\d+)*\b")),
)

_PLACEHOLDER_MARK = "@"


def _placeholder(index: int) -> str:
    """@1@, @2@, ... - see the module docstring for why this shape."""
    return f"{_PLACEHOLDER_MARK}{index + 1}{_PLACEHOLDER_MARK}"


def _placeholder_pattern(placeholder: str) -> re.Pattern[str]:
    """Match one placeholder however the model spaced or re-scripted it.

    A model may insert spaces (`@ 1 @`) or write the digit in the target
    script's numerals (`@१@`). It cannot make the placeholder mean
    something, so matching loosely is safe here in a way it would not be on
    real content.
    """
    pieces = []
    for character in placeholder:
        if character.isdigit():
            pieces.append(f"[{re.escape(digit_variants(character))}]")
        else:
            pieces.append(re.escape(character))
    return re.compile(r"\s*".join(pieces))


# Any placeholder-shaped token, for clearing out ones the model invented.
_ANY_PLACEHOLDER_RE = re.compile(
    rf"{re.escape(_PLACEHOLDER_MARK)}\s*[{re.escape(''.join(digit_variants(str(d)) for d in range(10)))}]{{1,3}}"
    rf"\s*{re.escape(_PLACEHOLDER_MARK)}"
)


@dataclass
class Protected:
    """The text with notation removed or masked, plus what was taken out."""

    text: str
    values: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.values


# What each direction protects, and why they differ.
#
# Into English, numbers stay in the sentence. A lifted number loses its unit:
# "500 लिटर" would translate to "litres" with the 500 appended
# somewhere else, and `extract_quantities` in is_advisor/requirements.py reads
# a number *adjacent to* its unit. Digits are folded to ASCII before this runs
# (detect.normalise), and translation models keep ASCII digits far more
# reliably than they keep an invented placeholder.
#
# Out of English, everything is protected: a human reads that text, and a
# reformatted digit in a displayed recommendation is a wrong answer.
LIFT_KINDS: tuple[str, ...] = ("citation", "code")
MASK_KINDS: tuple[str, ...] = ("citation", "code", "quantity", "number")


def _spans(text: str, kinds: tuple[str, ...] | None = None) -> list[tuple[int, int, str]]:
    """Non-overlapping protected spans, earliest and highest-priority first."""
    claimed: list[tuple[int, int, str]] = []
    for kind, pattern in _PROTECT_PATTERNS:
        if kinds is not None and kind not in kinds:
            continue
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(start < c_end and end > c_start for c_start, c_end, _ in claimed):
                continue
            claimed.append((start, end, kind))
    return sorted(claimed)


def lift(text: str, kinds: tuple[str, ...] = LIFT_KINDS) -> Protected:
    """Remove technical spans from `text`, keeping them in order.

    Used on the way *into* English: the prose is translated on its own and the
    lifted spans are re-attached afterwards by `reattach`.
    """
    text = text or ""
    spans = _spans(text, kinds)
    if not spans:
        return Protected(text=text)

    values, found_kinds, pieces, cursor = [], [], [], 0
    for start, end, kind in spans:
        pieces.append(text[cursor:start])
        values.append(text[start:end].strip())
        found_kinds.append(kind)
        cursor = end
    pieces.append(text[cursor:])
    stripped = re.sub(r"\s{2,}", " ", "".join(pieces)).strip(" ,;:-")
    return Protected(text=stripped, values=values, kinds=found_kinds)


def reattach(translated: str, protected: Protected) -> str:
    """Put the lifted notation back onto a translated query.

    Appended rather than reinserted at its original offset: the target is a
    retrieval query, where term presence is what counts, and an offset from
    the source sentence means nothing in a reordered translation.
    """
    if protected.is_empty:
        return translated.strip()
    tail = " ".join(protected.values)
    return f"{translated.strip()} {tail}".strip()


def mask(text: str, kinds: tuple[str, ...] = MASK_KINDS) -> Protected:
    """Replace technical spans with letter placeholders, keeping word order.

    Used on the way *out of* English, where a human reads the result.
    """
    text = text or ""
    spans = _spans(text, kinds)
    if not spans:
        return Protected(text=text)

    values, found_kinds, placeholders, pieces, cursor = [], [], [], [], 0
    for index, (start, end, kind) in enumerate(spans):
        placeholder = _placeholder(index)
        pieces.append(text[cursor:start])
        pieces.append(placeholder)
        values.append(text[start:end].strip())
        found_kinds.append(kind)
        placeholders.append(placeholder)
        cursor = end
    pieces.append(text[cursor:])
    return Protected(
        text="".join(pieces), values=values, kinds=found_kinds, placeholders=placeholders
    )


def unmask(translated: str, protected: Protected) -> tuple[str, list[str]]:
    """Restore masked values. Returns the text and the values it could not place.

    Tolerant on purpose: a translation model may space a placeholder out
    (`@ 1 @`) or write its digit in the target script's numerals. What it cannot
    do is make the placeholder mean something, so a fuzzy match is safe here in
    a way it would not be on real content.
    """
    text = translated or ""
    missing: list[str] = []
    for placeholder, value in zip(protected.placeholders, protected.values):
        pattern = _placeholder_pattern(placeholder)
        if pattern.search(text):
            text = pattern.sub(lambda _match, _value=value: _value, text, count=1)
        else:
            missing.append(value)
    # Any placeholder the model invented but we never issued would otherwise
    # be shown to a reader as gibberish.
    text = _ANY_PLACEHOLDER_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip(), missing
