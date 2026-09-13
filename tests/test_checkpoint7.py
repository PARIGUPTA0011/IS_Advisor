"""
Checkpoint 7: Grounding Validator. Builds real Evidence (retriever -> hydrate
-> live Neo4j KG expansion) for the test query, then feeds hand-constructed
RecommendationResponse objects through the validator - some intentionally
hallucinated, some genuinely grounded - and checks the verdicts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.grounding_validator import validate
from rag.kg_client import Neo4jKGClient
from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import expand_with_kg, hydrate
from rag.response_parser import DirectRecommendation, RecommendationResponse, RelatedStandard

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def main() -> None:
    store = MetadataStore()
    retriever = MockRetriever(store)
    kg = Neo4jKGClient.from_env()

    try:
        retrieved = retriever.retrieve(TEST_QUERY, top_k=5)
        evidence = hydrate(retrieved, store)
        expanded = expand_with_kg(evidence, kg)

        # Confirm the real facts this test depends on, before asserting.
        real_id = next(e.record.is_number for e in expanded if e.record and e.record.kys_id == 16790)  # IS 9421:1980
        real_related = next(
            (rel.is_number, rel.relationship)
            for e in expanded if e.record and e.record.kys_id == 16790
            for rel in e.kg_relations
        )
        recommended_id = next(e.record.is_number for e in expanded if e.record and e.record.kys_id == 22708)  # IS 16107...
        print(f"Ground truth from live pipeline: {real_id!r} has KG relation {real_related}")
        print(f"Ground truth: a genuinely retrieved, relevant standard: {recommended_id!r}\n")

        fake_response = RecommendationResponse(
            query=TEST_QUERY,
            direct_recommendations=[
                # 1. Hallucinated standard - does not exist anywhere in evidence
                DirectRecommendation(standard_id="IS 99999:2099", reason="This standard covers LED street lights."),
                # 2. Genuine standard, genuine evidence-tied reason - should be accepted
                DirectRecommendation(standard_id=recommended_id, reason="Title explicitly covers LED street lighting luminaires."),
                # 3. Genuine standard, but cites a clause that doesn't exist in evidence
                DirectRecommendation(standard_id=real_id, reason="As required under Clause 5.2 of this standard."),
            ],
            related_standards=[
                # 4. Hallucinated relationship type between two real standards
                RelatedStandard(standard_id=real_related[0], relationship="REPLACED_BY", related_to=real_id),
                # 5. Genuine relationship, taken directly from the live KG lookup above
                RelatedStandard(standard_id=real_related[0], relationship=real_related[1], related_to=real_id),
                # 6. Hallucinated standard entirely
                RelatedStandard(standard_id="IS 00000:1900", relationship="REFERENCES", related_to=real_id),
            ],
            warnings=[],
            confidence="high",
        )

        result = validate(fake_response, expanded)

        print("="*70)
        print("ACCEPTED direct recommendations:")
        for rec in result.accepted_recommendations:
            print(f"  ACCEPTED: {rec.standard_id} - {rec.reason}")
        print("\nREJECTED direct recommendations:")
        for rej in result.rejected_recommendations:
            print(f"  REJECTED/UNSUPPORTED: {rej.item.standard_id} - {rej.reason}")

        print("\nACCEPTED related standards:")
        for rel in result.accepted_related:
            print(f"  ACCEPTED: {rel.related_to} -{rel.relationship}-> {rel.standard_id}")
        print("\nREJECTED related standards:")
        for rej in result.rejected_related:
            print(f"  REJECTED/UNSUPPORTED: {rej.item.related_to} -{rej.item.relationship}-> {rej.item.standard_id} :: {rej.reason}")

        # --- Assertions ---
        accepted_ids = {r.standard_id for r in result.accepted_recommendations}
        rejected_ids = {r.item.standard_id for r in result.rejected_recommendations}

        assert "IS 99999:2099" in rejected_ids, "hallucinated standard must be rejected"
        assert recommended_id in accepted_ids, "genuine, well-grounded recommendation must be accepted"
        assert real_id in rejected_ids, "recommendation citing a nonexistent clause must be rejected"

        accepted_rel_pairs = {(r.related_to, r.relationship, r.standard_id) for r in result.accepted_related}
        rejected_rel_targets = {r.item.standard_id for r in result.rejected_related}

        assert (real_id, "REPLACED_BY", real_related[0]) not in accepted_rel_pairs, "hallucinated relationship type must not be accepted"
        assert real_related[0] in rejected_rel_targets, "hallucinated relationship type must be rejected"
        assert (real_id, real_related[1], real_related[0]) in accepted_rel_pairs, "genuine KG relationship must be accepted"
        assert "IS 00000:1900" in rejected_rel_targets, "hallucinated standard in a relationship must be rejected"

        print("\n[OK] every hallucinated standard_id, relationship, and clause citation was rejected")
        print("[OK] every genuinely grounded recommendation and relationship was accepted")
        print("\nCHECKPOINT 7: PASSED")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
