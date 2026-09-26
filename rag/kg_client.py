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
from neo4j import GraphDatabase, NotificationMinimumSeverity

from rag.schemas import RelatedStandard

REFERENCES = "REFERENCES"
REFERENCED_BY = "REFERENCED_BY"
REPLACED_BY = "REPLACED_BY"
REPLACES = "REPLACES"
# Clause 2 normative references, loaded by Knowlege_Graph/07. Stated by the
# standard itself, so kept apart from the scraped REFERENCES edges.
NORMATIVELY_REFERENCES = "NORMATIVELY_REFERENCES"

# Every relationship type Knowlege_Graph/02-06 creates. Counted by type rather
# than with one `MATCH ()-[r]->()` aggregation because naming the type lets
# Neo4j answer from its count store instead of scanning 200k relationships.
ALL_RELATIONSHIP_TYPES = (
    REFERENCES, REPLACED_BY, "BELONGS_TO", "MAINTAINED_BY", "REQUIRES_CERTIFICATION",
)

# An empty or half-loaded graph makes the server emit one notification per
# missing label, property and relationship type, per query - dozens of
# "Received notification from DBMS server" blocks that bury the actual result
# and say the same thing over and over. The real signal is "the graph is
# empty", which `describe_graph()` reports once, so the notifications are
# turned off at both ends: the server is asked not to raise them, and the
# driver is told not to log them. Set NEO4J_NOTIFICATIONS=1 to get them back
# when debugging a Cypher change.
def _notifications_enabled() -> bool:
    return (os.getenv("NEO4J_NOTIFICATIONS", "") or "").strip().lower() in {"1", "true", "yes", "on"}

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
    def __init__(self, uri: str, username: str, password: str, notifications: bool | None = None):
        show = _notifications_enabled() if notifications is None else notifications
        config = {} if show else {
            "notifications_min_severity": NotificationMinimumSeverity.OFF,
            "warn_notification_severity": NotificationMinimumSeverity.OFF,
        }
        self._driver = GraphDatabase.driver(uri, auth=(username, password), **config)

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

    def describe_graph(self) -> dict:
        """Node and relationship counts, and whether the graph is usable.

        Cheap enough to call at startup: each count names its label or
        relationship type, so Neo4j answers from the count store rather than
        scanning. `is_empty` is what a caller should branch on - it means the
        knowledge-graph half of every answer will be silently empty, which is
        otherwise only visible as `related_standards: []`.
        """
        counts: dict[str, int] = {}
        with self._driver.session() as session:
            for label in ("Standard", "Department", "Committee", "Certification"):
                counts[label] = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS count"
                ).single()["count"]
            relationships = {
                name: session.run(
                    f"MATCH ()-[r:{name}]->() RETURN count(r) AS count"
                ).single()["count"]
                for name in ALL_RELATIONSHIP_TYPES
            }
        return {
            "nodes": counts,
            "relationships": relationships,
            "standards": counts["Standard"],
            "is_empty": counts["Standard"] == 0,
        }

    def empty_graph_warning(self) -> str | None:
        """One sentence to print when the graph cannot answer anything, else None."""
        try:
            described = self.describe_graph()
        except Exception as error:                       # pragma: no cover
            return f"Could not check the knowledge graph: {type(error).__name__}: {error}"
        if not described["is_empty"]:
            return None
        return (
            "The Neo4j graph is empty (0 Standard nodes), so no related standards, "
            "replacement chains or reference edges can be returned - recommendations "
            "will still work, from retrieval alone. Load it with, from the repo root:\n"
            "  python Knowlege_Graph/02_create_graph.py\n"
            "  python Knowlege_Graph/03_create_relationships.py\n"
            "  python \"Knowlege_Graph/04_create_reference_relationships.py.py\"\n"
            "  python Knowlege_Graph/05_create_replacement_relationships.py\n"
            "  python Knowlege_Graph/06_create_certification_relationships.py"
        )

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
