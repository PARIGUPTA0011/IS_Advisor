"""
Checkpoint 5: LLM Generation. Runs the full pipeline (retriever -> hydrate
-> KG expansion -> context build -> prompt build -> LLM) for a real query
and prints the raw LLM output for inspection.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.context_builder import build_context
from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.metadata_store import MetadataStore
from rag.mock_retriever import MockRetriever
from rag.pipeline import expand_with_kg, hydrate
from rag.prompt_builder import build_prompt

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def main() -> None:
    store = MetadataStore()
    retriever = MockRetriever(store)
    kg = Neo4jKGClient.from_env()
    llm = get_llm_client()

    try:
        retrieved = retriever.retrieve(TEST_QUERY, top_k=5)
        evidence = hydrate(retrieved, store)
        expanded = expand_with_kg(evidence, kg)
        bundle = build_context(TEST_QUERY, expanded)
        system_prompt, user_message = build_prompt(bundle, store)

        print("="*70)
        print("SYSTEM PROMPT")
        print("="*70)
        print(system_prompt)

        print("="*70)
        print("USER MESSAGE (context)")
        print("="*70)
        print(user_message)

        print("="*70)
        print("RAW LLM OUTPUT")
        print("="*70)
        output = llm.generate(system_prompt, user_message)
        print(output)

        assert output.strip(), "LLM returned empty output"
        print("\nCHECKPOINT 5: PASSED (raw output above - manual inspection required)")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
