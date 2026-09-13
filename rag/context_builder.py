"""
Assembles the deterministic, structured context that gets handed to the LLM.

Three clearly separated sections, matching the brief:
  RETRIEVED EVIDENCE   - what semantic retrieval found (score, matched text)
  KNOWLEDGE GRAPH EVIDENCE - what the KG says is related to each retrieved standard
  STANDARD METADATA    - facts about each retrieved standard (status, dept, cert, ...)

Design choices:
  - Every evidence item gets a stable [N] tag reused across all three
    sections, so the LLM (and the grounding validator later) can trace a
    claim back to its source.
  - KG relations are capped per (standard, relationship type) - some
    standards have 30+ REFERENCES edges (Checkpoint 3), and dumping all of
    them would bloat the prompt without adding value.
  - Metadata rows only include fields that are actually non-null for that
    record - no padding the prompt with empty fields.
  - Nothing here is invented: every field printed traces back to a
    StandardRecord or RelatedStandard produced by earlier pipeline stages.
"""

from dataclasses import dataclass, field

from rag.metadata_store import MetadataStore
from rag.schemas import Evidence, StandardRecord

DEFAULT_MAX_RELATIONS_PER_TYPE = 5


@dataclass
class ContextBundle:
    query: str
    tags: list[str]                     # ["[1]", "[2]", ...] aligned with `evidence`
    evidence: list[Evidence]
    kg_lookup_failures: list[int] = field(default_factory=list)  # kys_ids the metadata store couldn't hydrate

    def to_prompt_text(self, metadata_store: MetadataStore, max_relations_per_type: int = DEFAULT_MAX_RELATIONS_PER_TYPE) -> str:
        lines: list[str] = []

        lines.append("USER QUERY")
        lines.append(self.query.strip())
        lines.append("")

        lines.append("RETRIEVED EVIDENCE")
        if not self.evidence:
            lines.append("(no standards retrieved for this query)")
        for tag, e in zip(self.tags, self.evidence):
            is_number = e.record.is_number if e.record else f"<unknown kys_id={e.kys_id}>"
            status = e.record.status if e.record else "unknown"
            title = e.record.title if e.record else "(title unavailable)"
            lines.append(f"{tag} {is_number}  (status={status}, score={e.score})")
            lines.append(f"    title: {title}")
            if e.matched_text and e.matched_text != title:
                lines.append(f"    matched_text: {e.matched_text!r}")
        lines.append("")

        lines.append("KNOWLEDGE GRAPH EVIDENCE")
        any_relations = False
        for tag, e in zip(self.tags, self.evidence):
            is_number = e.record.is_number if e.record else f"<unknown kys_id={e.kys_id}>"
            if not e.kg_relations:
                lines.append(f"{tag} {is_number}: (no KG relationships found)")
                continue

            any_relations = True
            lines.append(f"{tag} {is_number}:")
            by_type: dict[str, list] = {}
            for rel in e.kg_relations:
                by_type.setdefault(rel.relationship, []).append(rel)

            for rel_type in sorted(by_type):
                rels = by_type[rel_type]
                for rel in rels[:max_relations_per_type]:
                    related_record = metadata_store.get(rel.kys_id)
                    related_status = related_record.status if related_record else "unknown"
                    lines.append(f"    {rel_type} -> {rel.is_number} (status={related_status}) - {rel.title}")
                if len(rels) > max_relations_per_type:
                    lines.append(f"    ... and {len(rels) - max_relations_per_type} more {rel_type} relationships not shown")
        if not any_relations and self.evidence:
            lines.append("(none of the retrieved standards have KG relationships)")
        lines.append("")

        lines.append("STANDARD METADATA")
        for tag, e in zip(self.tags, self.evidence):
            if e.record is None:
                lines.append(f"{tag} <unknown kys_id={e.kys_id}>: no metadata available")
                continue
            fields = _non_empty_metadata_fields(e.record)
            if not fields:
                continue
            lines.append(f"{tag} {e.record.is_number}:")
            for key, value in fields.items():
                lines.append(f"    {key}: {value}")

        return "\n".join(lines)


def _non_empty_metadata_fields(record: StandardRecord) -> dict:
    """Only fields that exist and are non-empty for this record - title and
    status are already shown in RETRIEVED EVIDENCE, so they're excluded here
    to avoid duplication."""
    candidates = {
        "aspect": record.aspect,
        "department": record.department,
        "committee": record.committee,
        "group": record.group,
        "sub_group": record.sub_group,
        "sub_sub_group": record.sub_sub_group,
        "mandatory_cert": record.mandatory_cert,
        "certification": record.certification,
        "qco_status": record.qco_status,
        "qco_date": record.qco_date,
        "hs_codes": record.hs_codes,
        "ministries": record.ministries,
        "replaced_by_is": record.replaced_by_is,
        "revisions": record.revisions,
        "amendments_n": record.amendments_n,
        "reaffirmed_year": record.reaffirmed_year,
    }
    return {k: v for k, v in candidates.items() if v not in (None, "", "N/A")}


def build_context(query: str, evidence: list[Evidence]) -> ContextBundle:
    tags = [f"[{i + 1}]" for i in range(len(evidence))]
    return ContextBundle(query=query, tags=tags, evidence=evidence)
