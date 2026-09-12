"""Turn one procurement line into a labelled requirement object.

This exists mainly so the officer can see what was understood before being shown
standards. It is not a strong ranking signal and is not meant to be: measured
over the indexed titles, material words appear in 15.6% of them, property words
in 2.1% and environment words in 2.4%. Capacity and operating environment live
in clause 4 of the PDF, which this dataset does not carry. Nothing here is ever
used as a filter.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .gazetteer import find_terms

# --- quantities -------------------------------------------------------------

# Canonical unit spellings, so "litres", "litre" and "l" all report as "L".
_UNIT_ALIASES = {
    "l": "L", "ltr": "L", "ltrs": "L", "litre": "L", "litres": "L", "liter": "L", "liters": "L",
    "ml": "ml", "mm": "mm", "cm": "cm", "m": "m", "km": "km",
    "kg": "kg", "g": "g", "gm": "g", "gms": "g", "ton": "t", "tonne": "t", "tonnes": "t", "mt": "t",
    "kw": "kW", "w": "W", "watt": "W", "watts": "W", "kva": "kVA", "hp": "hp",
    "v": "V", "volt": "V", "volts": "V", "kv": "kV",
    "a": "A", "amp": "A", "amps": "A", "ampere": "A", "amperes": "A",
    "hz": "Hz", "mpa": "MPa", "bar": "bar", "psi": "psi", "kn": "kN", "n": "N",
    "sqm": "m2", "cum": "m3", "m2": "m2", "m3": "m3",
    "dn": "DN", "nb": "NB", "dia": "dia", "gauge": "gauge", "swg": "SWG",
    "degc": "degC", "lpd": "LPD", "lph": "LPH",
}
_UNIT_PATTERN = "|".join(sorted((re.escape(u) for u in _UNIT_ALIASES), key=len, reverse=True))

# An Indian-formatted number: 1,00,000 as readily as 1000 or 12.5.
_NUMBER = r"\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?"

_QUALIFIERS = {
    "minimum": "minimum", "min": "minimum", "at least": "minimum",
    "not less than": "minimum", "no less than": "minimum", "above": "minimum",
    "maximum": "maximum", "max": "maximum", "at most": "maximum",
    "not more than": "maximum", "no more than": "maximum", "up to": "maximum",
    "upto": "maximum", "below": "maximum", "not exceeding": "maximum",
}
_QUALIFIER_PATTERN = "|".join(sorted((re.escape(q) for q in _QUALIFIERS), key=len, reverse=True))

# The qualifier is often separated from the number by the thing being measured:
# "minimum capacity 500 litres". Up to two words are allowed in between.
_QUANTITY_RE = re.compile(
    rf"(?:(?P<qualifier>{_QUALIFIER_PATTERN})\s+(?:[a-z]+\s+){{0,2}})?"
    rf"(?P<value>{_NUMBER})"
    rf"(?:\s*(?:-|to|and)\s*(?P<value2>{_NUMBER}))?"
    rf"\s*(?P<unit>{_UNIT_PATTERN})\b",
    re.IGNORECASE,
)

# "DN 150", "NB 25", "M 12" put the unit first.
_PREFIX_UNIT_RE = re.compile(
    rf"\b(?P<unit>dn|nb|dia|gauge|swg)\s*(?P<value>{_NUMBER})\b", re.IGNORECASE
)

# What a unit measures, so that a field word nearby is only believed when it
# describes the same kind of thing. "32 mm diameter, quantity 45 MT" must not
# report the tonnage as a diameter.
_UNIT_DIMENSION = {
    "L": "volume", "ml": "volume", "m3": "volume", "LPD": "flow", "LPH": "flow",
    "m2": "area",
    "mm": "length", "cm": "length", "m": "length", "km": "length",
    "dia": "length", "DN": "length", "NB": "length", "gauge": "length", "SWG": "length",
    "kg": "mass", "g": "mass", "t": "mass",
    "kW": "power", "W": "power", "kVA": "power", "hp": "power",
    "V": "voltage", "kV": "voltage", "A": "current", "Hz": "frequency",
    "MPa": "pressure", "bar": "pressure", "psi": "pressure",
    "kN": "force", "N": "force", "degC": "temperature",
}
_FIELD_DIMENSION = {
    "capacity": "volume", "volume": "volume", "flow": "flow", "head": "length",
    "size": "length", "diameter": "length", "dia": "length", "bore": "length",
    "length": "length", "width": "length", "height": "length", "depth": "length",
    "thickness": "length", "weight": "mass", "mass": "mass",
    "power": "power", "rating": "power", "voltage": "voltage", "current": "current",
    "pressure": "pressure", "temperature": "temperature", "frequency": "frequency",
    "speed": "speed",
}

# Which measurement a unit describes when the line does not say.
_UNIT_FIELD = {
    "L": "capacity", "ml": "capacity", "LPD": "capacity", "LPH": "capacity",
    "m3": "capacity", "m2": "area",
    "mm": "size", "cm": "size", "m": "size", "km": "size", "dia": "diameter",
    "DN": "diameter", "NB": "diameter", "gauge": "gauge", "SWG": "gauge",
    "kg": "weight", "g": "weight", "t": "weight",
    "kW": "power", "W": "power", "kVA": "power", "hp": "power",
    "V": "voltage", "kV": "voltage", "A": "current", "Hz": "frequency",
    "MPa": "pressure", "bar": "pressure", "psi": "pressure",
    "kN": "force", "N": "force", "degC": "temperature",
}

# A field word just before the number overrides the unit's default.
_FIELD_WORDS = {
    "capacity", "volume", "size", "diameter", "dia", "bore", "length", "width",
    "height", "depth", "thickness", "weight", "mass", "power", "rating", "voltage",
    "current", "pressure", "temperature", "frequency", "speed", "flow", "head",
}

# Units that count things rather than measure them. "100 nos" is an order
# quantity, not a specification, and must never be read as a capacity.
_COUNT_WORDS = re.compile(r"\b(?:nos?|pcs|pieces?|units?|sets?|numbers?)\b", re.IGNORECASE)

# Only a count when a number introduces it. "2 sets" is an order quantity; the
# "set" in "pump set" is part of the product name and must survive.
_COUNT_PHRASE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)*\s*(?:nos?|pcs|pieces?|units?|sets?|numbers?)\b", re.IGNORECASE
)

# "resistant to corrosion" is the same requirement as "corrosion resistant",
# and only one of the two is how BIS words a title.
_REPHRASE = [
    (re.compile(r"\bresistant\s+to\s+(\w+)", re.IGNORECASE), r"\1 resistant"),
    (re.compile(r"\bresistance\s+to\s+(\w+)", re.IGNORECASE), r"\1 resistance"),
    (re.compile(r"\bproof\s+against\s+(\w+)", re.IGNORECASE), r"\1 proof"),
    (re.compile(r"\bmade\s+(?:out\s+)?of\s+", re.IGNORECASE), " "),
    (re.compile(r"\bmaterial\s+of\s+construction\b", re.IGNORECASE), " "),
]

# Leading imperatives in a procurement line: "Supply of 20 pumps".
_LEAD_VERBS = re.compile(
    r"^\s*(?:procure(?:ment)?|supply(?:ing)?|provide|provision|purchase|install(?:ation)?|"
    r"furnish|deliver(?:y)?|erect(?:ion)?|of|for)\b[\s:of]*",
    re.IGNORECASE,
)


@dataclass
class Quantity:
    value: float
    unit: str
    raw: str
    qualifier: str | None = None
    field: str | None = None
    value_max: float | None = None      # set when the line gives a range

    def to_dict(self) -> dict:
        out = asdict(self)
        return {k: v for k, v in out.items() if v is not None}


@dataclass
class Requirements:
    """What a line item asks for, as far as rules can tell."""
    product: str | None = None
    material: list[str] = field(default_factory=list)
    quantities: list[Quantity] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        out: dict = {"product": self.product}
        for name, value in (
            ("material", self.material),
            ("quantities", [q.to_dict() for q in self.quantities]),
            ("environment", self.environment),
            ("properties", self.properties),
            ("unmapped", self.unmapped),
        ):
            if value:
                out[name] = value
        return out

    def is_empty(self) -> bool:
        return not (self.product or self.material or self.quantities
                    or self.environment or self.properties)


# --- key/value mapping ------------------------------------------------------

_KEY_TO_FIELD = {
    "material": "material", "moc": "material", "material of construction": "material",
    "construction": "material", "body material": "material", "metallurgy": "material",
    "installation": "environment", "mounting": "environment", "location": "environment",
    "environment": "environment", "application": "environment", "service": "environment",
    "finish": "properties", "coating": "properties", "treatment": "properties",
    "protection": "properties", "property": "properties", "features": "properties",
}
_QUANTITY_KEYS = {
    "capacity", "size", "rating", "volume", "length", "width", "height", "depth",
    "thickness", "weight", "power", "voltage", "current", "pressure", "temperature",
    "diameter", "dia", "bore", "frequency", "speed", "flow", "head", "load",
}

# These name the product rather than describing it, and are consumed by product
# extraction. Listing them again under `unmapped` would report the product as
# something that could not be understood.
_PRODUCT_KEYS = {"product", "item", "description", "item description", "name", "equipment"}


def normalise(text: str) -> str:
    for pattern, replacement in _REPHRASE:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def extract_quantities(text: str) -> list[Quantity]:
    """Numbers with units, with their qualifier and what they measure."""
    found: list[Quantity] = []
    spans: list[tuple[int, int]] = []
    for match in _QUANTITY_RE.finditer(text or ""):
        unit = _UNIT_ALIASES.get(match.group("unit").lower())
        if unit is None:
            continue
        raw = match.group(0).strip()
        # A bare "m" or "a" next to a count word is almost always a false hit.
        if _COUNT_WORDS.search(text[max(0, match.start() - 12): match.end() + 12]) and unit in {"m", "A"}:
            continue
        qualifier_text = (match.group("qualifier") or "").lower().strip()
        preceding = re.findall(r"[a-z]+", text[: match.start()].lower())
        measured = None
        for word in reversed(preceding[-3:]):
            if word not in _FIELD_WORDS:
                continue
            candidate = "diameter" if word in {"dia", "bore"} else word
            # Only believe the nearby field word if it measures what this unit
            # measures; otherwise the unit's own default is more reliable.
            if _FIELD_DIMENSION.get(candidate) == _UNIT_DIMENSION.get(unit):
                measured = candidate
            break
        found.append(Quantity(
            value=_to_number(match.group("value")),
            unit=unit,
            raw=raw,
            qualifier=_QUALIFIERS.get(qualifier_text),
            field=measured or _UNIT_FIELD.get(unit),
            value_max=_to_number(match.group("value2")) if match.group("value2") else None,
        ))
        spans.append(match.span())

    for match in _PREFIX_UNIT_RE.finditer(text or ""):
        unit = _UNIT_ALIASES.get(match.group("unit").lower())
        if unit is None or any(q.raw == match.group(0).strip() for q in found):
            continue
        found.append(Quantity(
            value=_to_number(match.group("value")), unit=unit,
            raw=match.group(0).strip(), field=_UNIT_FIELD.get(unit),
        ))
        spans.append((match.start(), match.end()))
    return _merge_ranges(found, spans, text or "")


# Only these words between two measurements make them one range. Without this
# check, "25 mm bore and 40 mm pipe" would collapse into a single 25-to-40 range.
_RANGE_JOIN_RE = re.compile(r"^\s*(?:-|–|to|upto|up\s+to|and)\s*$", re.IGNORECASE)


def _merge_ranges(quantities: list[Quantity], spans: list[tuple[int, int]], text: str) -> list[Quantity]:
    """Fold "8 mm to 32 mm" into one range instead of two separate sizes."""
    merged: list[Quantity] = []
    merged_spans: list[tuple[int, int]] = []
    for quantity, span in zip(quantities, spans):
        if merged:
            previous, previous_span = merged[-1], merged_spans[-1]
            between = text[previous_span[1]: span[0]]
            if (previous.unit == quantity.unit and previous.value_max is None
                    and quantity.value > previous.value and _RANGE_JOIN_RE.match(between)):
                previous.value_max = quantity.value
                previous.raw = f"{previous.raw}{between}{quantity.raw}"
                merged_spans[-1] = (previous_span[0], span[1])
                continue
        merged.append(quantity)
        merged_spans.append(span)
    return merged


def _to_number(text: str) -> float:
    return float(text.replace(",", ""))


def extract_product(text: str, nlp=None, drop: list[str] | None = None) -> str | None:
    """The head noun phrase, once attributes and boilerplate are out of the way."""
    working = normalise(text or "")
    working = _QUANTITY_RE.sub(" ", working)
    working = _COUNT_PHRASE_RE.sub(" ", working)
    working = re.sub(r"\b\d+(?:[.,]\d+)*\b", " ", working)
    working = re.sub(r"\s+", " ", working).strip(" ,.-:;/")
    working = _LEAD_VERBS.sub("", working)
    if not working:
        return None

    # A procurement line leads with the product and then qualifies it, so the
    # span before the first comma or preposition is the product far more often
    # than any parser's first noun chunk. spaCy reads "pump set for borewell"
    # as a verb phrase and hands back "borewell".
    head = re.split(
        r"\s*[,;:]\s*|\s+(?:of|for|with|and|in|to|as|from|having|conforming|confirming|complying)\s+",
        working,
    )[0]
    head = re.sub(r"^(?:the|a|an|all|each|any)\s+", "", head.strip(), flags=re.IGNORECASE)
    head = _strip_leading_attributes(head, drop or [])
    # Cap first, then trim: trimming a seven-word phrase and then keeping five
    # words leaves the grade code the trim was meant to remove.
    words = _trim_specifiers(head.split()[:5])

    if not words and nlp is not None:
        for chunk in nlp(working).noun_chunks:
            words = _trim_specifiers(chunk.text.split()[:5])
            if words:
                break
    if not words:
        return None
    return singularise(" ".join(words))


def _strip_leading_attributes(head: str, attributes: list[str]) -> str:
    """Remove attribute words only where they lead the phrase.

    "stainless steel water storage tanks" is a tank made of stainless steel, so
    the material comes off. "Ordinary Portland Cement" is not a thing made of
    Portland cement, it is Portland cement, so removing the material wherever it
    appears would leave the product as "Ordinary".
    """
    changed = True
    while changed and head:
        changed = False
        for term in sorted(attributes, key=len, reverse=True):
            pattern = rf"^{re.escape(term)}\b[\s,-]*"
            stripped = re.sub(pattern, "", head, flags=re.IGNORECASE)
            if stripped != head:
                head, changed = stripped.strip(), True
                break
    return head


# Grade, model and dimension words trail the product name: "bars Fe 500D grade",
# "pipes class B", "blocks 80 mm thick". They qualify it, they do not name it.
_SPECIFIER_WORDS = frozenset({
    "grade", "grades", "class", "classes", "type", "types", "series", "size",
    "sizes", "make", "model", "variety", "quality", "spec", "specification",
    "thick", "thickness", "long", "length", "wide", "width", "high", "height",
    "deep", "depth", "dia", "diameter", "nominal", "bore", "duty", "rated",
    "medium", "heavy", "light", "standard",
})


def _trim_specifiers(words: list[str]) -> list[str]:
    trimmed = [w.strip(" ,.-:;/") for w in words]
    trimmed = [w for w in trimmed if w]
    while trimmed:
        last = trimmed[-1].lower()
        if last in _SPECIFIER_WORDS or any(ch.isdigit() for ch in last) or len(last) <= 2:
            trimmed.pop()
            continue
        break
    return trimmed


def singularise(phrase: str) -> str:
    """Crude plural stripping on the head word only. 'tanks' -> 'tank'."""
    words = phrase.split()
    if not words:
        return phrase
    head = words[-1]
    lowered = head.lower()
    if lowered.endswith("ies") and len(head) > 4:
        head = head[:-3] + "y"
    elif re.search(r"(?:ss|us|is)$", lowered):
        pass
    elif re.search(r"(?:ches|shes|xes|ses)$", lowered):
        head = head[:-2]
    elif lowered.endswith("s") and len(head) > 3:
        head = head[:-1]
    return " ".join(words[:-1] + [head])


def from_pairs(pairs: list[tuple[str, str]]) -> Requirements:
    """Requirements from a specification block, where the key names the field.

    Nothing is inferred here: `Material: Stainless steel` says what it is.
    """
    requirements = Requirements()
    for key, value in pairs:
        normalised = key.strip().lower()
        if normalised in _PRODUCT_KEYS:
            continue                    # consumed by product extraction
        target = _KEY_TO_FIELD.get(normalised)

        if target == "material":
            requirements.material.extend(_split_values(value))
        elif target == "environment":
            requirements.environment.extend(_split_values(value))
        elif target == "properties":
            requirements.properties.extend(_split_values(value))
        elif normalised in _QUANTITY_KEYS or target is None:
            quantities = extract_quantities(f"{normalised} {value}")
            if quantities:
                for quantity in quantities:
                    if normalised in _QUANTITY_KEYS:
                        quantity.field = "diameter" if normalised in {"dia", "bore"} else normalised
                requirements.quantities.extend(quantities)
            elif normalised not in _QUANTITY_KEYS:
                # Unrecognised key with a non-numeric value: keep it, labelled,
                # rather than dropping information the officer typed.
                requirements.unmapped.append(f"{key.strip()}: {value}")
    return requirements


def _split_values(value: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\s*(?:,|/|;|\band\b)\s*", value) if p.strip()]
    return parts or [value.strip()]


def extract(text: str, pairs: list[tuple[str, str]] | None = None, nlp=None) -> Requirements:
    """Full extraction for one line item.

    `text` should be the original line rather than the boilerplate-stripped
    query, because stripping removes the quantities this needs to read.
    """
    requirements = from_pairs(pairs or [])
    normalised = normalise(text or "")

    for kind, target in (("material", requirements.material),
                         ("property", requirements.properties),
                         ("environment", requirements.environment)):
        for term in find_terms(normalised, kind):
            if term not in (t.lower() for t in target):
                target.append(term)

    if not requirements.quantities:
        requirements.quantities = extract_quantities(normalised)

    product_source = None
    for key, value in pairs or []:
        if key.strip().lower() in _PRODUCT_KEYS:
            product_source = value
            break
    drop = list(requirements.material) + list(requirements.properties) + list(requirements.environment)
    requirements.product = extract_product(product_source or normalised, nlp=nlp, drop=drop)
    return requirements
