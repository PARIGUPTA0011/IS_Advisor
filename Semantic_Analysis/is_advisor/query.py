"""Query side: turn a tender document into clean, searchable line items.

Splitting a tender is a structural problem, not a semantic one, so this is all
rules. Never embed a whole tender as one vector - averaging six products into
one point in space retrieves none of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# "IS 1786", "IS 1786:2008", "IS 2911 (Part 1)", "IS/ISO 9001:2015", "IS 1234 Part 2"
IS_NUMBER_RE = re.compile(
    r"\bIS(?:\s*/\s*(?:ISO|IEC|TS|TR|QC|EN))*\s*[:.]?\s*"
    r"(\d{1,5})"
    r"(?:\s*\(?\s*Part\s*(\d+)\s*\)?)?"
    r"(?:\s*\(?\s*Sec(?:tion)?\s*(\d+)\s*\)?)?"
    r"(?:\s*[:\-]\s*((?:19|20)\d{2}))?",
    re.IGNORECASE,
)

# Bullets and numbering mark an item boundary; the marker itself is then dropped.
_BULLET_RE = re.compile(r"^\s*(?:[-*•●▪‣>]+|\(?[a-z0-9]{1,3}[.)])\s+", re.IGNORECASE)
_ROW_SPLIT_RE = re.compile(r"[\n\r]+|(?<=[a-z0-9])\s*;\s*(?=[A-Za-z])")
# A table row is one line item; '|' only separates cells inside it, so pipes
# are flattened to spaces rather than treated as a boundary.
_CELL_RE = re.compile(r"\|{1,2}")

# Procurement boilerplate. These phrases appear in every tender and match every
# standard equally, so they only add noise to both BM25 and the embedding.
_BOILERPLATE_PATTERNS = [
    r"\b(?:shall|should|must|will|to)\s+(?:be\s+)?(?:suppl(?:y|ied)|provide[d]?|deliver(?:ed)?|conform(?:ing|s)?|compl(?:y|ying|ies)|manufactur(?:e|ed)|use[d]?|make|made|quote[d]?)\b",
    r"\b(?:as\s+per|in\s+accordance\s+with|conform(?:ing|s)?\s+to|complying\s+with|compliant\s+with|confirming\s+to)\b",
    r"\b(?:make|brand|model)\s*[:/-]\s*[\w .-]{0,30}",
    r"\b(?:bidder|tenderer|supplier|vendor|contractor|purchaser|consignee|firm)s?\b",
    # Every alternative here ends on a word boundary. Without one, "no" matches
    # inside "nominal" and "notice", quietly corrupting the product description.
    r"\b(?:quantity|qty|nos|no|units?|rate|price|amount|cost|gst|tax|inr|rs)\b\.?\s*[:.]?\s*[\d,./%-]*",
    r"\b(?:delivery|warranty|guarantee|payment|tender|bid|emd|contract|schedule|annexure|clause)\b",
    r"\bitem\s+(?:no\b\.?|code\b)\s*[\w/-]*",
    r"\b(?:latest|current|amended|revised)\s+(?:version|edition|amendment)\b",
    r"\bor\s+equivalent\b",
    r"\b(?:with\s+)?ISI\s+mark(?:ed|ing)?\b",
    r"\b(?:approved|reputed|standard)\s+(?:make|brand|quality)\b",
]
_BOILERPLATE_RE = re.compile("|".join(_BOILERPLATE_PATTERNS), re.IGNORECASE)

_UNIT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:mm|cm|m|km|kg|gm?|g|ton(?:ne)?s?|mt|ltr?s?|l|ml|nos|pcs|pieces|"
    r"sets?|sqm|cum|m2|m3|kw|kva|kv|volts?|v|amps?|amperes?|hz|watts?|w|bar|psi|inch(?:es)?|ft)\b",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")

_MIN_ITEM_CHARS = 8


@dataclass
class LineItem:
    """One procurement line, plus what the rules managed to pull out of it."""
    raw: str
    text: str                      # boilerplate stripped, used for retrieval
    cited_is: list[str] = field(default_factory=list)
    keyphrases: list[str] = field(default_factory=list)
    # Key/value pairs when this item came from a specification block. The key
    # already names the field, so downstream extraction needs no inference here.
    pairs: list[tuple[str, str]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.text) < 3


@dataclass
class Segment:
    """A stretch of the document that becomes exactly one line item."""
    text: str
    pairs: list[tuple[str, str]] = field(default_factory=list)


def normalise_is_number(match: re.Match) -> str:
    """Render a matched citation in dataset `is_base_id` form."""
    number, part, section, _year = match.groups()
    out = f"IS {int(number)}"
    if part:
        out += f" (Part {int(part)})"
    if section:
        out += f" (Sec {int(section)})"
    return out


def extract_is_numbers(text: str) -> list[str]:
    """Base ids cited in the text, in order, deduplicated."""
    found: list[str] = []
    for match in IS_NUMBER_RE.finditer(text):
        base = normalise_is_number(match)
        if base not in found:
            found.append(base)
    return found


def strip_boilerplate(text: str, drop_citations: bool = True) -> str:
    """Remove procurement filler. Citations go too: they are matched exactly
    elsewhere, and their digits only add noise to the semantic query."""
    if drop_citations:
        text = IS_NUMBER_RE.sub(" ", text)
    text = _BOILERPLATE_RE.sub(" ", text)
    text = _UNIT_RE.sub(" ", text)
    text = re.sub(r"[\d,]{4,}", " ", text)          # bare quantities and prices
    text = re.sub(r"[^\w\s()/&.+-]", " ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip(" .,-:;/")


# "Capacity: 200 L" - a labelled attribute, not a procurement line of its own.
# The value must be non-empty, which is what separates an attribute from a bare
# heading like "Technical Specification:".
_KV_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 /()&.-]{0,30})\s*:\s*(\S.*?)\s*$")
_MIN_KV_BLOCK_LINES = 2

# Keys whose value names the product rather than describing it.
_PRODUCT_KEYS = frozenset({"product", "item", "description", "item description",
                           "material description", "name", "equipment"})

# Commercial keys. Their values are kept in `pairs` for display but stay out of
# the query: "2 years" and "30 days" describe the contract, not the product.
_COMMERCIAL_KEYS = frozenset({
    "warranty", "guarantee", "delivery", "delivery period", "delivery schedule",
    "payment", "payment terms", "price", "rate", "cost", "amount", "gst", "tax",
    "quantity", "qty", "nos", "units", "make", "brand", "model", "supplier",
    "vendor", "bidder", "emd", "validity", "hsn", "hsn code",
})


def parse_kv_block(lines: list[str]) -> list[tuple[str, str]]:
    """Parse consecutive `Key: value` lines into ordered pairs."""
    pairs: list[tuple[str, str]] = []
    for line in lines:
        match = _KV_LINE_RE.match(line)
        if match:
            pairs.append((match.group(1).strip(), match.group(2).strip()))
    return pairs


def _kv_block_text(pairs: list[tuple[str, str]], title: str | None) -> str:
    """Build one searchable line from a specification block.

    A block describes a single product, so it has to retrieve as a single query.
    Searching "Material: Stainless steel" on its own returns stainless steel
    standards that have nothing to do with the tank being procured.
    """
    product = title
    values: list[str] = []
    for key, value in pairs:
        normalised = key.strip().lower()
        if product is None and normalised in _PRODUCT_KEYS:
            product = value
            continue
        if normalised in _COMMERCIAL_KEYS:
            continue
        values.append(value)
    parts = ([product] if product else []) + values
    return ", ".join(p for p in parts if p)


def segment_document(document: str) -> list[Segment]:
    """Split a document into segments, each of which becomes one line item.

    Runs ahead of the line splitter so that a specification block is recognised
    before newline splitting takes it apart.
    """
    lines = (document or "").splitlines()
    segments: list[Segment] = []
    index = 0

    while index < len(lines):
        run_end = index
        while run_end < len(lines) and _is_kv_line(lines[run_end]):
            run_end += 1

        if run_end - index >= _MIN_KV_BLOCK_LINES:
            pairs = parse_kv_block(lines[index:run_end])
            title = _absorb_title(segments)
            segments.append(Segment(text=_kv_block_text(pairs, title), pairs=pairs))
            index = run_end
            continue

        for text in _split_plain_line(lines[index]):
            segments.append(Segment(text=text))
        index += 1

    if not segments and (document or "").strip():
        # A short question is the single-item case.
        segments = [Segment(text=document.strip())]
    return segments


def _is_kv_line(line: str) -> bool:
    return bool(_KV_LINE_RE.match(line)) and not _BULLET_RE.match(line)


def _absorb_title(segments: list[Segment]) -> str | None:
    """Take the line immediately above a block as the product name, if it is one.

    "Solar water heater, residential" above a block of attributes names the
    product. "Technical Specification:" above the same block is a heading and
    must not become the product name.
    """
    if not segments or segments[-1].pairs:
        return None
    candidate = segments[-1].text.strip()
    if not candidate or is_heading(candidate, []):
        return None
    if len(candidate.split()) > 12:
        return None                     # a paragraph, not a title line
    segments.pop()
    return candidate


def _split_plain_line(line: str) -> list[str]:
    """Apply the row, cell and sub-item rules to one physical line."""
    chunks: list[str] = []
    for raw_row in _ROW_SPLIT_RE.split(line or ""):
        row = _CELL_RE.sub(" ", raw_row or "").strip()
        if not row:
            continue
        for part in _split_subitems(row):
            cleaned = _BULLET_RE.sub("", part).strip()
            if len(cleaned) >= _MIN_ITEM_CHARS:
                chunks.append(cleaned)
    return chunks


def split_line_items(document: str) -> list[str]:
    """Split a tender into candidate line items on structural markers only."""
    return [segment.text for segment in segment_document(document)]


# A numbered marker right after one of these words is part of a reference
# ("IS 8329 (Part 1)"), not the start of a new procurement item.
_NOT_A_SUBITEM_AFTER = frozenset({"part", "sec", "section", "clause", "table", "fig", "figure", "grade", "type", "class"})
_SUBITEM_MARK_RE = re.compile(r"(?<=[a-z0-9)\].,])\s+(?=\(?[a-z0-9]{1,3}[.)]\s)", re.IGNORECASE)


def _split_subitems(row: str) -> list[str]:
    """Split one physical line that holds several numbered sub-items."""
    cuts = [0]
    for match in _SUBITEM_MARK_RE.finditer(row):
        preceding = re.findall(r"[A-Za-z]+", row[: match.start()])
        if preceding and preceding[-1].lower() in _NOT_A_SUBITEM_AFTER:
            continue
        cuts.append(match.start())
    cuts.append(len(row))
    return [row[a:b] for a, b in zip(cuts, cuts[1:]) if row[a:b].strip()]


def _keyphrases(text: str, nlp=None) -> list[str]:
    if nlp is not None:
        doc = nlp(text)
        phrases = [chunk.text.strip() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 2]
        if phrases:
            return phrases[:8]
    # Fallback when spaCy is unavailable: split on function words, keep content.
    return [p.strip() for p in re.split(r"\s+(?:of|for|with|and|in|to)\s+", text) if len(p.strip()) > 3][:8]


def load_spacy(model: str = "en_core_web_sm"):
    """Return a spaCy pipeline, or None if spaCy or the model is not installed."""
    try:
        import spacy
        return spacy.load(model, disable=["ner", "lemmatizer"])
    except Exception:
        return None


def is_heading(raw: str, cited: list[str]) -> bool:
    """Section headings describe no product, so retrieving against them only
    produces confident nonsense ("NOTICE INVITING TENDER" -> whatever is nearest
    in vector space). A heading that cites a standard is kept, since the
    citation is still worth resolving."""
    if cited:
        return False
    stripped = raw.strip()
    if stripped.endswith(":"):
        return True
    letters = [c for c in stripped if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(stripped.split()) <= 6:
        return True
    return False


def parse_document(document: str, nlp=None) -> list[LineItem]:
    """Full query-side pass: split, strip, and pull out citations and phrases."""
    items: list[LineItem] = []
    for segment in segment_document(document):
        raw, pairs = segment.text, segment.pairs
        cited = extract_is_numbers(raw)
        if not pairs and is_heading(raw, cited):
            continue
        text = strip_boilerplate(raw)
        if len(text) < 3:
            # Nothing left but a citation - still worth resolving that citation.
            if not cited:
                continue
            text = raw.strip()
        items.append(LineItem(
            raw=raw, text=text, cited_is=cited,
            keyphrases=_keyphrases(text, nlp), pairs=pairs,
        ))
    return items
