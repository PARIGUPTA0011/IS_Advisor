"""
RAG pipeline orchestration. Built incrementally, checkpoint by checkpoint.
Checkpoint 2 wires: Retriever -> hydrate() -> Evidence.
Checkpoint 3 adds: expand_with_kg() -> Evidence.kg_relations populated.
Checkpoint 8 adds: run_query(), the end-to-end orchestrator, including the
no-evidence short circuit (never call the LLM with nothing to ground on).
"""

import dataclasses
from dataclasses import dataclass, field

from rag.context_builder import build_context
from rag.grounding_validator import ValidationResult, validate
from rag.kg_client import KGClient
from rag.llm_client import LLMClient
from rag.metadata_store import MetadataStore
from rag.prompt_builder import build_prompt
from rag.response_parser import RecommendationResponse, parse_response
from rag.retriever_interface import Retriever, RetrievedEvidence, validate_retrieved_evidence
from rag.schemas import Evidence


def hydrate(
    retrieved: list[RetrievedEvidence],
    metadata_store: MetadataStore,
) -> list[Evidence]:
    """Turn bare retriever output into full Evidence by looking up each
    kys_id in the metadata store. This is the seam where the RAG pipeline
    starts depending on real standard data instead of the retriever's
    internal representation."""

    validate_retrieved_evidence(retrieved)

    evidence: list[Evidence] = []
    for item in retrieved:
        kys_id = item["kys_id"]
        record = metadata_store.get(kys_id)
        evidence.append(
            Evidence(
                kys_id=kys_id,
                score=item["score"],
                matched_text=item.get("matched_text"),
                record=record,
                why=item.get("why"),
                tier=item.get("tier"),
            )
        )
    return evidence


def expand_with_kg(evidence: list[Evidence], kg_client: KGClient) -> list[Evidence]:
    """For each piece of retrieved evidence, look up its KG neighbors
    (REFERENCES / REFERENCED_BY / REPLACED_BY / REPLACES) and attach them.
    Evidence is frozen, so this returns new instances rather than mutating."""

    expanded: list[Evidence] = []
    for e in evidence:
        relations = kg_client.get_relationships(e.kys_id)
        expanded.append(dataclasses.replace(e, kg_relations=relations))
    return expanded


@dataclass
class PipelineResult:
    response: RecommendationResponse
    validation: ValidationResult | None
    evidence: list[Evidence] = field(default_factory=list)
    short_circuited: bool = False  # True if the LLM was never called (no retrieval evidence)


def run_query(
    query: str,
    retriever: Retriever,
    metadata_store: MetadataStore,
    kg_client: KGClient,
    llm_client: LLMClient,
    top_k: int = 10,
) -> PipelineResult:
    """End-to-end orchestration: Retriever -> hydrate -> KG expand ->
    context -> prompt -> LLM -> parse -> validate.

    If retrieval finds nothing, the LLM is never called: there would be
    nothing to ground a response in, and calling it anyway risks the model
    falling back on its own parametric knowledge instead of admitting
    insufficient evidence. This is a deliberate short circuit, not a
    missing feature.
    """

    retrieved = retriever.retrieve(query, top_k=top_k)
    validate_retrieved_evidence(retrieved)

    if not retrieved:
        response = RecommendationResponse(
            query=query,
            warnings=["No relevant standards were found for this query. The specification "
                      "may be too vague, out of scope for the indexed standards, or use "
                      "terminology that doesn't match any standard title."],
            confidence="insufficient_evidence",
        )
        return PipelineResult(response=response, validation=None, evidence=[], short_circuited=True)

    evidence = hydrate(retrieved, metadata_store)
    evidence = expand_with_kg(evidence, kg_client)

    bundle = build_context(query, evidence)
    system_prompt, user_message = build_prompt(bundle, metadata_store)
    raw_output = llm_client.generate(system_prompt, user_message, json_mode=True)
    response = parse_response(query, raw_output)

    validation = validate(response, evidence)
    # Grounding is enforced here, not just measured: anything the validator
    # rejected is dropped from the response returned to the caller.
    response.direct_recommendations = validation.accepted_recommendations
    response.related_standards = validation.accepted_related
    if validation.has_rejections:
        response.warnings = list(response.warnings) + [
            f"{len(validation.rejected_recommendations) + len(validation.rejected_related)} "
            "unsupported claim(s) from the model were rejected by the grounding validator."
        ]

    return PipelineResult(response=response, validation=validation, evidence=evidence, short_circuited=False)
