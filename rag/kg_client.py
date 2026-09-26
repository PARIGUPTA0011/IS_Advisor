"""
Knowledge Graph client for the RAG pipeline.

Reuses the exact Neo4j schema populated by Knowlege_Graph/02-06 (see KG.md):
labels Standard/Department/Committee/Certification, relationship types
REFERENCES, REPLACED_BY, BELONGS_TO, MAINTAINED_BY, REQUIRES_CERTIFICATION.

Scope note: get_relationships() surfaces standard-to-standard graph edges
only (REFERENCES / REFERENCED_BY / REPLACED_BY / REPLACES) - the relations
that add genuinely new "related standards" evidence. BELONGS_TO,
MAINTAINED_BY and REQUIRES_CERTIFICATION are organizational/certification
facts about a single standard, not related-standard edges, and are already
exposed directly on StandardRecord (department, committee, mandatory_cert,
certification) via the metadata store - so they are not duplicated here.
"""

import os
from typing import Protocol

from dotenv import load_dotenv
from neo4j import GraphDatabase

from rag.schemas import RelatedStandard

REFERENCES = "REFERENCES"
REFERENCED_BY = "REFERENCED_BY"
REPLACED_BY = "REPLACED_BY"
REPLACES = "REPLACES"
# Clause 2 normative references, loaded by Knowlege_Graph/07. Stated by the
# standard itself, so kept apart from the scraped REFERENCES edges.
NORMATIVELY_REFERENCES = "NORMATIVELY_REFERENCES"

_QUERY = """
MATCH (s:Standard {kys_id: $kys_id})
CALL (s) {
    MATCH (s)-[:REFERENCES]->(t:Standard)
    RETURN collect(DISTINCT {kys_id: t.kys_id, is_number: t.is_number, title: t.title}) AS refs
}
CALL (s) {
    MATCH (s)<-[:REFERENCES]-(t:Standard)
    RETURN collect(DISTINCT {kys_id: t.kys_id, is_number: t.is_number, title: t.title}) AS ref_by
}
CALL (s) {
    MATCH (s)-[:REPLACED_BY]->(t:Standard)
    RETURN collect(DISTINCT {kys_id: t.kys_id, is_number: t.is_number, title: t.title}) AS replaced_by
}
CALL (s) {
    MATCH (s)<-[:REPLACED_BY]-(t:Standard)
    RETURN collect(DISTINCT {kys_id: t.kys_id, is_number: t.is_number, title: t.title}) AS replaces
}
CALL (s) {
    OPTIONAL MATCH (s)-[:NORMATIVELY_REFERENCES]->(t:Standard)
    RETURN collect(DISTINCT {kys_id: t.kys_id, is_number: t.is_number, title: t.title}) AS normative
}
RETURN refs, ref_by, replaced_by, replaces, normative
"""


class KGClient(Protocol):
    def get_relationships(self, kys_id: int) -> list[RelatedStandard]: ...
    def close(self) -> None: ...


def _to_related(items: list[dict], relationship: str) -> list[RelatedStandard]:
    return [
        RelatedStandard(
            kys_id=item["kys_id"],
            is_number=item["is_number"] or "",
            title=item["title"] or "",
            relationship=relationship,
        )
        for item in items
        if item.get("kys_id") is not None
    ]


class Neo4jKGClient:
    def __init__(self, uri: str, username: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    @classmethod
    def from_env(cls) -> "Neo4jKGClient":
        load_dotenv()
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        if not (uri and username and password):
            raise RuntimeError(
                "NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD must be set (.env or environment)"
            )
        return cls(uri, username, password)

    def close(self) -> None:
        self._driver.close()

    def get_relationships(self, kys_id: int) -> list[RelatedStandard]:
        with self._driver.session() as session:
            record = session.run(_QUERY, kys_id=kys_id).single()

        if record is None:
            return []

        related: list[RelatedStandard] = []
        related += _to_related(record["refs"], REFERENCES)
        related += _to_related(record["ref_by"], REFERENCED_BY)
        related += _to_related(record["replaced_by"], REPLACED_BY)
        related += _to_related(record["replaces"], REPLACES)
        related += _to_related(record["normative"], NORMATIVELY_REFERENCES)
        return related


def get_kg_client() -> KGClient:
    """Neo4j when it is configured and reachable, the local CSV graph otherwise.

    Both answer get_relationships() from the same data and rules, so the
    pipeline behaves the same either way; only Neo4j needs the network.
    Set KG_BACKEND=local to force the offline graph (for a demo), or
    KG_BACKEND=neo4j to fail loudly instead of falling back.
    """
    load_dotenv()
    backend = os.getenv("KG_BACKEND", "auto").lower()
    if backend != "local":
        try:
            client = Neo4jKGClient.from_env()
            client._driver.verify_connectivity()
            return client
        except Exception as exc:
            if backend == "neo4j":
                raise
            print(f"Neo4j unavailable ({exc.__class__.__name__}); using the local CSV graph.")
    from rag.local_kg_client import LocalKGClient

    return LocalKGClient()
