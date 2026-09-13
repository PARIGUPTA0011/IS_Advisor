"""
Checkpoint 4: Context Builder. Runs the full Checkpoint 2+3 pipeline
(MockRetriever -> hydrate -> expand_with_kg against live Neo4j) then builds
the exact context text that would be sent to the LLM, and inspects it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.context_builder import build_context
from rag.kg_client import Neo4jKGClient
from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import expand_with_kg, hydrate

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def main() -> None:
    store = MetadataStore()
    retriever = MockRetriever(store)
    kg = Neo4jKGClient.from_env()

    try:
        retrieved = retriever.retrieve(TEST_QUERY, top_k=5)
        evidence = hydrate(retrieved, store)
        expanded = expand_with_kg(evidence, kg)

        bundle = build_context(TEST_QUERY, expanded)
        context_text = bundle.to_prompt_text(store)

        print(context_text)
        print(f"\n{'='*70}")
        print(f"Context length: {len(context_text)} chars")

        # --- Checks ---

        # 1. No giant/irrelevant context: bounded even though one retrieved
        #    standard (kys_id=14886) has 35 raw KG relationships.
        assert len(context_text) < 6000, f"context is too large: {len(context_text)} chars"

        # 2. Standard IDs preserved verbatim for every retrieved evidence item.
        for e in expanded:
            assert e.record is not None
            assert e.record.is_number in context_text, f"missing is_number {e.record.is_number}"

        # 3. KG relationships are capped, not dumped wholesale, for the
        #    standard we know has 32 REFERENCES (Checkpoint 3).
        capped_note_present = "more REFERENCES relationships not shown" in context_text
        assert capped_note_present, "expected a capped/truncation note for the 32-REFERENCES standard"

        # 4. Traceability: the same [N] tag must appear in all three
        #    sections for every evidence item (so a claim can be traced to
        #    its evidence, KG relations, and metadata).
        for tag in bundle.tags:
            count = context_text.count(tag)
            assert count >= 3, f"tag {tag} should appear in all 3 sections, found {count} times"

        # 5. No duplicate info where avoidable: title should not be repeated
        #    inside the STANDARD METADATA section (it's already shown once
        #    in RETRIEVED EVIDENCE).
        metadata_section = context_text.split("STANDARD METADATA")[1]
        assert "title:" not in metadata_section, "title should not be duplicated in STANDARD METADATA"

        # 6. Section headers all present and in the documented order.
        for header in ["USER QUERY", "RETRIEVED EVIDENCE", "KNOWLEDGE GRAPH EVIDENCE", "STANDARD METADATA"]:
            assert header in context_text
        assert context_text.index("RETRIEVED EVIDENCE") < context_text.index("KNOWLEDGE GRAPH EVIDENCE")
        assert context_text.index("KNOWLEDGE GRAPH EVIDENCE") < context_text.index("STANDARD METADATA")

        print("\n[OK] context is bounded, traceable, deduplicated, and correctly ordered")
        print("\nCHECKPOINT 4: PASSED")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
