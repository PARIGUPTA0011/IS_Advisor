"""
Internal RAG data structures. Field names match what was actually verified to
exist in IS_Standards_Data/standards.jsonl and standards.csv (Checkpoint 0) -
no invented fields.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class StandardRecord:
    """Hydrated metadata for one standard, keyed by kys_id. Source of truth:
    standards.jsonl / standards.csv. This is what the retriever's bare
    (kys_id, score) gets expanded into."""

    kys_id: int
    is_number: str
    title: str
    status: Optional[str] = None          # "current" | "withdrawn" | None
    # Edition identity. `is_number` is one edition ("IS 2062:2011"); `is_base_id`
    # is the standard across editions ("IS 2062"). Both are dataset columns, not
    # derived here - rag/kg_editions.py needs them to tell a superseded edition
    # from a different standard.
    is_base_id: Optional[str] = None
    is_year: Optional[int] = None
    is_canonical: Optional[bool] = None
    aspect: Optional[str] = None
    department: Optional[str] = None
    committee: Optional[str] = None
    group: Optional[str] = None
    sub_group: Optional[str] = None
    sub_sub_group: Optional[str] = None
    mandatory_cert: Optional[bool] = None
    certification: Optional[str] = None
    qco_status: Optional[str] = None
    qco_date: Optional[str] = None
    hs_codes: Optional[str] = None
    ministries: Optional[str] = None
    replaced_by_id: Optional[int] = None
    replaced_by_is: Optional[str] = None
    revisions: Optional[str] = None
    amendments_n: Optional[str] = None
    reaffirmed_year: Optional[str] = None


@dataclass(frozen=True)
class RelatedStandard:
    """One KG neighbor of a standard. relationship is one of the 7 types
    that actually exist in the graph schema (see Knowlege_Graph/KG.md):
    REFERENCES, REFERENCED_BY, REPLACED_BY, REPLACES, BELONGS_TO,
    MAINTAINED_BY, REQUIRES_CERTIFICATION."""

    kys_id: int
    is_number: str
    title: str
    relationship: str
    # Filled by rag/kg_editions.py from the metadata store, because the graph
    # nodes do not carry the last two. A None status means the standard was not
    # found in the store, which is different from "current".
    status: Optional[str] = None
    is_base_id: Optional[str] = None
    is_year: Optional[int] = None


@dataclass(frozen=True)
class Evidence:
    """One piece of RAG evidence: retrieval result + hydrated metadata,
    combined. This is what the context builder consumes."""

    kys_id: int
    score: float
    matched_text: Optional[str]
    record: Optional[StandardRecord]      # None if kys_id wasn't found in the metadata store
    kg_relations: list[RelatedStandard] = field(default_factory=list)
    why: Optional[str] = None             # Retriever's own explanation, if it provides one (e.g. SemanticRetriever)
    tier: Optional[str] = None            # Retriever's own relevance band, if it provides one
