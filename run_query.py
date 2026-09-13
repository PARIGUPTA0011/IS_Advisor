"""
Quick manual test runner for the RAG pipeline.

Usage:
    python run_query.py "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."
"""

import sys

from rag.metadata_store import MetadataStore
from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python run_query.py "your query here"')
        sys.exit(1)

    query = sys.argv[1]

    store = MetadataStore()
    retriever = get_retriever(store)
    kg = Neo4jKGClient.from_env()
    llm = get_llm_client()

    try:
        result = run_query(query, retriever, store, kg, llm, top_k=5)
    finally:
        kg.close()

    print("QUERY:", query)
    print()
    print("CONFIDENCE:", result.response.confidence)
    print()
    print("DIRECT RECOMMENDATIONS:")
    for r in result.response.direct_recommendations:
        print(f"  - {r.standard_id} (status={r.status}) [{r.evidence_tag}]")
        print(f"    reason: {r.reason}")
    print()
    print("RELATED STANDARDS:")
    for r in result.response.related_standards:
        print(f"  - {r.standard_id} --{r.relationship}--> {r.related_to}")
        print(f"    reason: {r.reason}")
    print()
    print("WARNINGS:", result.response.warnings)
    print()
    print("RETRIEVED EVIDENCE:")
    for e in result.evidence:
        title = e.record.title if e.record else "?"
        is_number = e.record.is_number if e.record else "?"
        print(f"  kys_id={e.kys_id} score={e.score:.4f} {is_number}  {title[:70]}")


if __name__ == "__main__":
    main()
