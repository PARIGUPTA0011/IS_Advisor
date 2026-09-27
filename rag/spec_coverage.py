"""Which specification values in the query the evidence cannot confirm.

A query says `90W LED street light IP66`. The evidence is title and metadata
level - `IS 16107 (Part 2/Sec 2):2017 Luminaries Performance Part 2 Particular
Requirements Section 2 LED Street Lighting` - and contains no IP rating, no
wattage and no clause text at all. So the honest answer is "this standard covers
LED street lighting luminaires; whether it specifies IP66 is not something this
evidence shows", and that caveat belongs on every such answer.

It used to appear only when the model happened to mention it: one run warned
about IP66 and the next, same query, did not. A caveat that shows up at random
is worse than none, because its absence reads as confirmation. So it is computed
here instead - a pure function of the query text and the evidence, with the same
answer every time - and the prompt's version of the instruction is now a
belt-and-braces second line rather than the only one.

**The spec patterns are not defined here.** They come from
`multilingual.protect`, which already had to decide what counts as technical
notation in order to protect it across a translation. One definition, used by
both, so a grade code that survives translation is also a grade code here.

Coverage is checked by squashing whitespace and case out of both sides, so
`IP 66` in a title counts as covering `IP66` in the query. It cannot do better
than that: matching an IP rating to a standard that *implies* it without
naming it needs the clause text this dataset does not carry
(`Semantic_Analysis/README.md` section 13).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.schemas import Evidence

# How many terms to name before summarising. A query with a dozen values makes a
# warning nobody reads; the first few plus a count is the readable form.
MAX_TERMS_LISTED = 6

# Bare numbers and IS citations are excluded on purpose. A bare "500" carries no
# claim on its own, and a citation is not a specification value - it is resolved
# and reported separately, by name, in cited_standards.
SPEC_KINDS = ("code", "quantity")

_SQUASH_RE = re.compile(r"[\s\-_/]+")


@dataclass(frozen=True)
class SpecTerm:
    """One specification value from the query, and whether evidence names it."""

    text: str                  # as written in the query, e.g. "IP66"
    kind: str                  # "code" or "quantity", from multilingual.protect
    covered_by: str | None     # the IS number whose text contains it, if any

    @property
    def covered(self) -> bool:
        return self.covered_by is not None


def _squash(text: str) -> str:
    """Lowercase and remove the separators that stop `IP 66` matching `IP66`."""
    return _SQUASH_RE.sub("", (text or "").lower())


def _evidence_text(evidence: Evidence) -> str:
    """Everything about one standard that a spec value could legitimately appear in."""
    record = evidence.record
    if record is None:
        return evidence.matched_text or ""
    parts = [
        record.is_number, record.title, record.aspect, record.group,
        record.sub_group, record.sub_sub_group, record.certification,
        record.qco_status, evidence.matched_text,
    ]
    # KG neighbours count too: a related standard's title naming the value is
    # still the evidence naming it.
    parts += [relation.title for relation in evidence.kg_relations]
    parts += [relation.is_number for relation in evidence.kg_relations]
    return " ".join(part for part in parts if part)


def extract_spec_terms(query: str) -> list[SpecTerm]:
    """Specification values in the query, deduplicated, in order of appearance."""
    from multilingual import protect

    lifted = protect.lift(query or "", kinds=SPEC_KINDS)
    terms: list[SpecTerm] = []
    seen: set[str] = set()
    for value, kind in zip(lifted.values, lifted.kinds):
        key = _squash(value)
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(SpecTerm(text=value, kind=kind, covered_by=None))
    return terms


def check_coverage(query: str, evidence: list[Evidence]) -> list[SpecTerm]:
    """Every spec term in the query, each marked with the standard that names it."""
    terms = extract_spec_terms(query)
    if not terms:
        return []

    haystacks = [
        (
            (item.record.is_number if item.record else f"kys_id={item.kys_id}"),
            _squash(_evidence_text(item)),
        )
        for item in evidence
    ]

    resolved: list[SpecTerm] = []
    for term in terms:
        needle = _squash(term.text)
        match = next((is_number for is_number, text in haystacks if needle in text), None)
        resolved.append(SpecTerm(text=term.text, kind=term.kind, covered_by=match))
    return resolved


def unsupported_terms(query: str, evidence: list[Evidence]) -> list[str]:
    """Just the spec values no evidence line names, as written in the query."""
    return [term.text for term in check_coverage(query, evidence) if not term.covered]


def coverage_warning(query: str, evidence: list[Evidence]) -> str | None:
    """One sentence naming the unconfirmed values, or None if there are none.

    Deliberately not phrased as a failure. The standards may well specify these
    values; this dataset simply cannot show that they do, and conflating "not
    evidenced" with "not compliant" would be its own kind of wrong.
    """
    if not evidence:
        return None
    missing = unsupported_terms(query, evidence)
    if not missing:
        return None

    listed = ", ".join(missing[:MAX_TERMS_LISTED])
    if len(missing) > MAX_TERMS_LISTED:
        listed += f", and {len(missing) - MAX_TERMS_LISTED} more"
    return (
        f"The evidence does not state these values from the query: {listed}. "
        "The indexed data is title and metadata level only - it carries no clause "
        "text - so the standards above are recommended on scope, not on those "
        "values being confirmed. Check the standard itself before relying on them."
    )
