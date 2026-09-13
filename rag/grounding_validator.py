"""
Post-generation grounding validator. This is the enforcement layer behind
the prompt's grounding rules (rag/prompt_builder.py) - the prompt asks the
LLM to only cite supplied evidence; this module checks that it actually did,
and rejects (never silently accepts) anything it can't verify.

Checks performed, mapped to the checkpoint's four requirements:
  1. Every direct recommendation's standard_id must appear in the retrieved
     evidence (Evidence.record.is_number).
  2. No recommendation may cite a clause/section number - the dataset has
     no clause-level text (Checkpoint 0), so any such citation is by
     construction unsupported.
  3. Every related-standard relationship must match an actual
     (standard, relationship, standard) triple from the KG evidence
     attached to the retrieved standards.
  4. Anything failing 1-3 is rejected with a reason, never silently kept.
"""

import re
from dataclasses import dataclass, field

from rag.response_parser import DirectRecommendation, RecommendationResponse, RelatedStandard
from rag.schemas import Evidence

_CLAUSE_PATTERN = re.compile(r"\b(clause|sub-clause|subclause|section|sec\.?)\s*[\d.]+", re.IGNORECASE)


@dataclass
class RejectedItem:
    item: object
    reason: str


@dataclass
class ValidationResult:
    accepted_recommendations: list[DirectRecommendation] = field(default_factory=list)
    rejected_recommendations: list[RejectedItem] = field(default_factory=list)
    accepted_related: list[RelatedStandard] = field(default_factory=list)
    rejected_related: list[RejectedItem] = field(default_factory=list)

    @property
    def has_rejections(self) -> bool:
        return bool(self.rejected_recommendations or self.rejected_related)


def _cites_unsupported_clause(text: str | None, title: str | None) -> bool:
    """True if `text` cites a clause/section number that isn't just the
    model quoting the standard's own title. Standard numbers/titles
    routinely contain "Part 2", "Sec 3", etc. (e.g. "IS 16107 (Part 2/Sec 2)")
    - that's a legitimate reference to retrieved evidence, not a fabricated
    internal clause citation, so only flag a match that doesn't also appear
    in the title."""
    if not text:
        return False
    title = title or ""
    for match in _CLAUSE_PATTERN.finditer(text):
        if match.group(0).lower() not in title.lower():
            return True
    return False


def validate(response: RecommendationResponse, evidence: list[Evidence]) -> ValidationResult:
    retrieved_ids = {e.record.is_number for e in evidence if e.record}
    kg_neighbor_ids = {rel.is_number for e in evidence for rel in e.kg_relations}
    known_ids = retrieved_ids | kg_neighbor_ids
    titles_by_id = {e.record.is_number: e.record.title for e in evidence if e.record}

    # Every (source_is_number, relationship, target_is_number) triple that
    # genuinely exists in the KG evidence attached to this response.
    valid_triples = {
        (e.record.is_number, rel.relationship, rel.is_number)
        for e in evidence
        if e.record
        for rel in e.kg_relations
    }

    result = ValidationResult()

    for rec in response.direct_recommendations:
        if rec.standard_id not in retrieved_ids:
            result.rejected_recommendations.append(
                RejectedItem(rec, f"standard_id {rec.standard_id!r} does not appear in RETRIEVED EVIDENCE")
            )
            continue
        if _cites_unsupported_clause(rec.reason, titles_by_id.get(rec.standard_id)):
            result.rejected_recommendations.append(
                RejectedItem(rec, "reason cites a clause/section number not present in the standard's title, "
                                   "and no clause-level data is available in evidence")
            )
            continue
        result.accepted_recommendations.append(rec)

    for rel in response.related_standards:
        if rel.standard_id not in known_ids:
            result.rejected_related.append(
                RejectedItem(rel, f"standard_id {rel.standard_id!r} does not appear in RETRIEVED EVIDENCE or KNOWLEDGE GRAPH EVIDENCE")
            )
            continue
        if rel.related_to not in known_ids:
            result.rejected_related.append(
                RejectedItem(rel, f"related_to {rel.related_to!r} does not appear in RETRIEVED EVIDENCE or KNOWLEDGE GRAPH EVIDENCE")
            )
            continue
        # Schema direction is (standard_id -[relationship]-> related_to), matching
        # the KG's own (source, relationship, target) triples - but both orderings
        # are accepted since relationship phrasing direction isn't load-bearing here.
        forward = (rel.standard_id, rel.relationship, rel.related_to)
        backward = (rel.related_to, rel.relationship, rel.standard_id)
        if forward not in valid_triples and backward not in valid_triples:
            result.rejected_related.append(
                RejectedItem(
                    rel,
                    f"relationship {rel.relationship!r} between {rel.related_to!r} and {rel.standard_id!r} "
                    "was not found in KNOWLEDGE GRAPH EVIDENCE",
                )
            )
            continue
        result.accepted_related.append(rel)

    return result
