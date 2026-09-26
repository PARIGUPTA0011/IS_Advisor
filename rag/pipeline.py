"""
RAG pipeline orchestration. Built incrementally, checkpoint by checkpoint.
Checkpoint 2 wires: Retriever -> hydrate() -> Evidence.
Checkpoint 3 adds: expand_with_kg() -> Evidence.kg_relations populated.
Checkpoint 8 adds: run_query(), the end-to-end orchestrator, including the
no-evidence short circuit (never call the LLM with nothing to ground on).

Multilingual support wraps this, it does not thread through it. A non-English
query is translated to English before retrieval and the answer is translated
back after validation, so every stage in between - retrieval, KG expansion,
the prompt, the LLM, the grounding validator - runs on exactly the English it
was built and tested against. That ordering is load-bearing: the validator in
grounding_validator.py matches IS numbers and clause patterns in the model's
prose, and it cannot do that in a language it is not written for. Translating
before validation would mean validating nothing.
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
    # Present for any query, English included, so a caller can always report
    # what language was detected and how.
    detection: dict | None = None
    translation: dict | None = None


def localise_response(response: RecommendationResponse, target: str | None) -> RecommendationResponse:
    """Translate the displayed text of a validated response. Runs last.

    Only what the model or the pipeline *wrote* is translated: reasons,
    warnings, the status word. Identifiers (`standard_id`) and relationship
    names (`REFERENCES`, `REPLACED_BY`) keep their English values, because the
    first is an identifier and the second is matched against the knowledge
    graph's own labels.
    """
    from multilingual.localize import Localizer

    localizer = Localizer(target)
    response.language = localizer.describe()
    if not localizer.active:
        return response

    # One model call for every string in the answer. See Localizer.prime.
    localizer.prime(
        [rec.reason for rec in response.direct_recommendations]
        + [rec.status for rec in response.direct_recommendations]
        + [rec.reason for rec in response.related_standards]
        + list(response.warnings)
    )

    for rec in response.direct_recommendations:
        rec.reason_localized = localizer.plain(rec.reason)
        rec.status_localized = localizer.plain_label(rec.status) if rec.status else None
    for rec in response.related_standards:
        rec.reason_localized = localizer.plain(rec.reason) if rec.reason else None
    response.warnings_localized = [localizer.plain(warning) for warning in response.warnings]
    return response


def run_query(
    query: str,
    retriever: Retriever,
    metadata_store: MetadataStore,
    kg_client: KGClient,
    llm_client: LLMClient,
    top_k: int = 10,
    language: str | None = None,
) -> PipelineResult:
    """End-to-end orchestration: detect -> translate -> Retriever -> hydrate ->
    KG expand -> context -> prompt -> LLM -> parse -> validate -> localise.

    If retrieval finds nothing, the LLM is never called: there would be
    nothing to ground a response in, and calling it anyway risks the model
    falling back on its own parametric knowledge instead of admitting
    insufficient evidence. This is a deliberate short circuit, not a
    missing feature.

    `language` forces the input and output language; omitted, it is detected
    from the query. The answer comes back in that language, with IS numbers and
    official titles left in English.
    """

    from multilingual import prepare_query

    detection, translation, english_query = prepare_query(query, language)
    target_language = language or detection.code

    retrieved = retriever.retrieve(english_query, top_k=top_k)
    validate_retrieved_evidence(retrieved)

    if not retrieved:
        response = RecommendationResponse(
            query=query,
            query_english=english_query if english_query != query else None,
            warnings=["No relevant standards were found for this query. The specification "
                      "may be too vague, out of scope for the indexed standards, or use "
                      "terminology that doesn't match any standard title."],
            confidence="insufficient_evidence",
        )
        return PipelineResult(
            response=localise_response(response, target_language),
            validation=None,
            evidence=[],
            short_circuited=True,
            detection=detection.to_dict(),
            translation=translation.to_dict(),
        )

    evidence = hydrate(retrieved, metadata_store)
    evidence = expand_with_kg(evidence, kg_client)

    # The English query goes into the context, not the original: the evidence
    # block and the prompt's grounding rules are English, and a model asked to
    # reason in one language about evidence in another is being set up to
    # paraphrase rather than cite.
    bundle = build_context(english_query, evidence)
    system_prompt, user_message = build_prompt(bundle, metadata_store)
    raw_output = llm_client.generate(system_prompt, user_message, json_mode=True)
    response = parse_response(query, raw_output)
    response.query_english = english_query if english_query != query else None

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

    # Localisation is the last step, after the validator has had its say on
    # English text. See the module docstring.
    response = localise_response(response, target_language)

    return PipelineResult(
        response=response,
        validation=validation,
        evidence=evidence,
        short_circuited=False,
        detection=detection.to_dict(),
        translation=translation.to_dict(),
    )
