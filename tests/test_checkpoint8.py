"""
Checkpoint 8: No-Evidence & Ambiguous Queries. Runs run_query() (the full
orchestrated pipeline, Checkpoint 8's new addition) for three real queries
of deliberately different evidence strength.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import run_query

QUERY_NO_EVIDENCE = "zzqxv blorptastic nonexistent widget flibbertigibbet"
QUERY_AMBIGUOUS = "I need a pump for industrial use."
QUERY_STRONG = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def main() -> None:
    store = MetadataStore()
    retriever = MockRetriever(store)
    kg = Neo4jKGClient.from_env()
    llm = get_llm_client()

    try:
        print("="*70)
        print("TEST A - No evidence")
        print("="*70)
        result_a = run_query(QUERY_NO_EVIDENCE, retriever, store, kg, llm)
        print(f"short_circuited={result_a.short_circuited}")
        print(f"confidence={result_a.response.confidence}")
        print(f"direct_recommendations={result_a.response.direct_recommendations}")
        print(f"warnings={result_a.response.warnings}")
        assert result_a.short_circuited is True, "no-evidence query must short-circuit before calling the LLM"
        assert result_a.response.confidence == "insufficient_evidence"
        assert result_a.response.direct_recommendations == [], "must not fabricate a recommendation with zero evidence"

        print("\n" + "="*70)
        print("TEST B - Ambiguous specification")
        print("="*70)
        result_b = run_query(QUERY_AMBIGUOUS, retriever, store, kg, llm, top_k=8)
        print(f"short_circuited={result_b.short_circuited}")
        print(f"confidence={result_b.response.confidence}")
        print(f"direct_recommendations:")
        for rec in result_b.response.direct_recommendations:
            print(f"  - {rec.standard_id}: {rec.reason}")
        print(f"warnings={result_b.response.warnings}")
        assert result_b.short_circuited is False, "weak evidence is still evidence - the LLM should see it and hedge"
        # Ambiguous case must not be reported with unwarranted confidence
        assert result_b.response.confidence in ("low", "medium", "insufficient_evidence"), (
            f"expected a cautious confidence level for an ambiguous query, got {result_b.response.confidence!r}"
        )

        print("\n" + "="*70)
        print("TEST C - Strong specification")
        print("="*70)
        result_c = run_query(QUERY_STRONG, retriever, store, kg, llm)
        print(f"short_circuited={result_c.short_circuited}")
        print(f"confidence={result_c.response.confidence}")
        print(f"direct_recommendations:")
        for rec in result_c.response.direct_recommendations:
            print(f"  - {rec.standard_id}: {rec.reason}")
        print(f"warnings={result_c.response.warnings}")
        assert result_c.short_circuited is False
        assert len(result_c.response.direct_recommendations) >= 1, "strong evidence should yield at least one recommendation"
        assert result_c.response.confidence != "insufficient_evidence"

        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"{'Query':<12} {'Evidence':<10} {'Confidence':<20} {'#Recs'}")
        print(f"{'A (none)':<12} {'none':<10} {result_a.response.confidence:<20} {len(result_a.response.direct_recommendations)}")
        print(f"{'B (weak)':<12} {'weak':<10} {result_b.response.confidence:<20} {len(result_b.response.direct_recommendations)}")
        print(f"{'C (strong)':<12} {'strong':<10} {result_c.response.confidence:<20} {len(result_c.response.direct_recommendations)}")

        print("\n[OK] no evidence -> short-circuited, no fabricated recommendation")
        print("[OK] weak/ambiguous evidence -> cautious confidence, not overconfident")
        print("[OK] strong evidence -> confident, grounded recommendation")
        print("\nCHECKPOINT 8: PASSED")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
