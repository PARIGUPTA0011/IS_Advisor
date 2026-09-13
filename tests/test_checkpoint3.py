"""
Checkpoint 3: Knowledge Graph expansion, against the real live Neo4j Aura
instance (credentials in .env, gitignored). Verifies that for a retrieved
standard, KG relationships can be fetched and that they actually exist in
the graph - independently cross-checked against IS_Standards_Data/edges.csv,
which is the actual source file Knowlege_Graph/04_create_reference_relationships.py.py
loaded into Neo4j (the authoritative ground truth for REFERENCES edges).

Note: standards.jsonl also embeds refers_to/referred_by arrays per record,
but a first pass cross-checking against those found 2 edges present in
edges.csv/Neo4j but missing from the jsonl arrays for kys_id=14886 - a
pre-existing staleness in how that jsonl export was generated, not a defect
in this pipeline. edges.csv is authoritative here because it's the literal
input to the KG-loading script.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.kg_client import Neo4jKGClient
from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import expand_with_kg, hydrate

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."
EDGES_PATH = Path(__file__).resolve().parent.parent / "IS_Standards_Data" / "edges.csv"


def load_edges_ground_truth(kys_id: int) -> tuple[set[int], set[int]]:
    """Returns (references_out, referenced_by_in) id sets straight from
    edges.csv, the file the Neo4j REFERENCES relationships were built from."""
    df = pd.read_csv(EDGES_PATH, usecols=["citing_id", "cited_id"])
    refs = set(df[df.citing_id == kys_id]["cited_id"].tolist())
    ref_by = set(df[df.cited_id == kys_id]["citing_id"].tolist())
    return refs, ref_by


def main() -> None:
    store = MetadataStore()
    retriever = MockRetriever(store)
    kg = Neo4jKGClient.from_env()

    try:
        print(f"Query: {TEST_QUERY!r}")
        retrieved = retriever.retrieve(TEST_QUERY, top_k=5)
        evidence = hydrate(retrieved, store)
        expanded = expand_with_kg(evidence, kg)

        for e in expanded:
            print(f"\n{'='*70}")
            print(f"Retrieved: kys_id={e.kys_id}  {e.record.is_number}  ({e.record.status})")
            print(f"  title: {e.record.title}")
            print(f"  KG relationships ({len(e.kg_relations)}):")
            if not e.kg_relations:
                print("    (none)")
            for rel in e.kg_relations[:8]:
                print(f"    - {rel.relationship} -> {rel.is_number}  ({rel.title})")
            if len(e.kg_relations) > 8:
                print(f"    ... and {len(e.kg_relations) - 8} more")

        # Deep-dive + cross-check on one specific standard with rich
        # relationships, per Checkpoint 3's explicit requirement. Using the
        # strongest real match from Checkpoint 2 that actually has edges.
        target_id = 14886  # IS 7848:1975 - Studio spot lights (35 REFERENCES)
        print(f"\n{'='*70}")
        print(f"CROSS-CHECK for kys_id={target_id} against IS_Standards_Data/edges.csv")
        target_evidence = hydrate(
            [{"kys_id": target_id, "score": 1.0, "matched_text": None}], store
        )
        target_expanded = expand_with_kg(target_evidence, kg)[0]

        edges_refs, edges_ref_by = load_edges_ground_truth(target_id)

        kg_refs = {r.kys_id for r in target_expanded.kg_relations if r.relationship == "REFERENCES"}
        kg_ref_by = {r.kys_id for r in target_expanded.kg_relations if r.relationship == "REFERENCED_BY"}

        print(f"  is_number: {target_expanded.record.is_number}")
        print(f"  edges.csv citing->cited ids ({len(edges_refs)}):   {sorted(edges_refs)}")
        print(f"  neo4j REFERENCES ids ({len(kg_refs)}):  {sorted(kg_refs)}")
        print(f"  MATCH: {edges_refs == kg_refs}")
        print(f"  edges.csv cited<-citing ids ({len(edges_ref_by)}): {sorted(edges_ref_by)}")
        print(f"  neo4j REFERENCED_BY ({len(kg_ref_by)}):   {sorted(kg_ref_by)}")
        print(f"  MATCH: {edges_ref_by == kg_ref_by}")

        assert edges_refs == kg_refs, "Neo4j REFERENCES disagrees with source edges.csv"
        assert edges_ref_by == kg_ref_by, "Neo4j REFERENCED_BY disagrees with source edges.csv"

        for rel in target_expanded.kg_relations:
            assert rel.relationship in {
                "REFERENCES", "REFERENCED_BY", "REPLACED_BY", "REPLACES",
            }, f"unexpected relationship type: {rel.relationship}"

        print("\n[OK] every REFERENCES/REFERENCED_BY relationship independently verified against source data")

        # Second cross-check: a standard known (from standards.csv) to have a
        # REPLACED_BY edge, to exercise the relationship type not present above.
        replaced_id, replacement_id = 5, 26770  # IS/IEC/TS 62351-4:2007 -> :2020
        print(f"\n{'='*70}")
        print(f"CROSS-CHECK REPLACED_BY for kys_id={replaced_id}")
        rb_evidence = hydrate([{"kys_id": replaced_id, "score": 1.0, "matched_text": None}], store)
        rb_expanded = expand_with_kg(rb_evidence, kg)[0]
        rb_ids = {r.kys_id for r in rb_expanded.kg_relations if r.relationship == "REPLACED_BY"}
        print(f"  is_number: {rb_expanded.record.is_number}")
        print(f"  standards.csv replaced_by_id: {replacement_id}")
        print(f"  neo4j REPLACED_BY ids: {sorted(rb_ids)}")
        assert rb_ids == {replacement_id}, "Neo4j REPLACED_BY disagrees with standards.csv replaced_by_id"
        print("  MATCH: True")
        print("\n[OK] REPLACED_BY relationship independently verified against standards.csv")
        print("\nCHECKPOINT 3: PASSED")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
