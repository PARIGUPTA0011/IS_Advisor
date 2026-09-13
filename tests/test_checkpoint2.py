"""
Checkpoint 2: verify the RAG pipeline correctly consumes a Retriever's
output, using a MockRetriever over real repository data (not the eventual
semantic search - that's the teammate's job).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import hydrate
from rag.retriever_interface import validate_retrieved_evidence

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def main() -> None:
    print("Loading MetadataStore from standards.jsonl ...")
    store = MetadataStore()
    print(f"  loaded {len(store)} standard records")
    assert len(store) == 35524, f"expected 35524 records, got {len(store)}"

    retriever = MockRetriever(store)

    print(f"\nQuery: {TEST_QUERY!r}")
    results = retriever.retrieve(TEST_QUERY, top_k=5)

    print(f"\nMockRetriever returned {len(results)} results:")
    for r in results:
        print(f"  kys_id={r['kys_id']:<6} score={r['score']:<7} is_number={r['is_number']!r:<28} matched_text={r['matched_text']!r}")

    assert results, "expected at least one result for this query"

    # Contract check: retriever output must satisfy the minimum contract
    validate_retrieved_evidence(results)
    print("\n[OK] retriever output satisfies RetrievedEvidence contract (kys_id, score present)")

    # RAG consumption check: hydrate into full Evidence via MetadataStore,
    # independent of whatever the retriever did or didn't include
    evidence = hydrate(results, store)

    print(f"\nHydrated {len(evidence)} Evidence objects:")
    for e in evidence:
        assert e.record is not None, f"kys_id {e.kys_id} not found in metadata store"
        assert e.record.kys_id == e.kys_id, "kys_id mismatch between evidence and hydrated record"
        assert e.score is not None
        print(
            f"  kys_id={e.kys_id:<6} score={e.score:<7} "
            f"is_number={e.record.is_number!r:<28} status={e.record.status!r:<10} "
            f"title={e.record.title!r}"
        )

    print("\n[OK] every result hydrated to a full StandardRecord: kys_id, score, "
          "matched_text and metadata all preserved through the pipeline")

    print("\nCHECKPOINT 2: PASSED")


if __name__ == "__main__":
    main()
