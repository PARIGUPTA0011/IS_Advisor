"""
Checkpoint 6: Structured Output. Runs the full pipeline and parses the LLM's
JSON response into RecommendationResponse, then verifies malformed LLM
output is handled safely instead of crashing the pipeline.
"""

import dataclasses
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
from rag.response_parser import parse_response

TEST_QUERY = "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."


def test_malformed_inputs() -> None:
    print("="*70)
    print("Malformed-response handling (no live call needed)")
    print("="*70)

    cases = [
        "not json at all, just prose explaining the answer",
        '```json\n{"direct_recommendations": [{"standard_id": "IS 123:2020", "reason": "test"}], "warnings": [], "confidence": "high"}\n```',
        '{"direct_recommendations": [{"standard_id": "IS 999:1999"}], "confidence": "high"',  # truncated/invalid JSON
        '{"direct_recommendations": "not a list", "confidence": "high"}',  # wrong type
    ]
    for i, raw in enumerate(cases, 1):
        result = parse_response(TEST_QUERY, raw)
        print(f"\nCase {i}: {raw[:60]!r}...")
        print(f"  -> confidence={result.confidence!r}, "
              f"direct_recommendations={len(result.direct_recommendations)}, "
              f"warnings={result.warnings}")
        assert isinstance(result.confidence, str)
        assert isinstance(result.direct_recommendations, list)

    # Case 2 (valid fenced JSON) must parse successfully, not error out
    good = parse_response(TEST_QUERY, cases[1])
    assert good.confidence == "high"
    assert len(good.direct_recommendations) == 1
    assert good.direct_recommendations[0].standard_id == "IS 123:2020"

    # Cases 1, 3, 4 must degrade safely, never raise
    for raw in [cases[0], cases[2], cases[3]]:
        result = parse_response(TEST_QUERY, raw)
        assert result.confidence in ("parse_error",), f"expected parse_error for {raw!r}, got {result.confidence}"

    print("\n[OK] malformed/edge-case LLM output never crashes the parser and degrades to confidence='parse_error'")


def main() -> None:
    test_malformed_inputs()

    print("\n" + "="*70)
    print("Live end-to-end structured output")
    print("="*70)

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

        raw_output = llm.generate(system_prompt, user_message, json_mode=True)
        print("\nRAW LLM OUTPUT (should be pure JSON):")
        print(raw_output)

        result = parse_response(TEST_QUERY, raw_output)

        print("\nPARSED STRUCTURED OUTPUT:")
        import json
        print(json.dumps(dataclasses.asdict(result), indent=2))

        # --- Checks ---
        assert result.confidence != "parse_error", f"live LLM output failed to parse: {raw_output!r}"

        valid_is_numbers = {e.record.is_number for e in expanded if e.record}
        for rec in result.direct_recommendations:
            assert rec.standard_id in valid_is_numbers, (
                f"direct recommendation {rec.standard_id!r} not in retrieved evidence {valid_is_numbers}"
            )
            assert rec.reason, "every recommendation must have a non-empty reason"

        print("\n[OK] response is valid JSON, required fields present, "
              "every recommended standard_id traces back to retrieved evidence")
        print("\nCHECKPOINT 6: PASSED")
    finally:
        kg.close()


if __name__ == "__main__":
    main()
