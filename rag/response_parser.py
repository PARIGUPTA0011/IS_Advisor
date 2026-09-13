"""
Structured output for the RAG pipeline.

Schema is deliberately close to the brief's suggested shape but adapted to
what's actually in this dataset: no clause-level text exists (Checkpoint 0),
so there's no "clause evidence" field - only standard_id + reason tied to
title/metadata/KG relationship. `evidence_tag` (the [N] from the context
builder) lets the grounding validator (Checkpoint 7) trace every claim back
to a specific piece of evidence without re-matching text.

Malformed LLM output is handled safely: parse_response() never raises for
bad JSON - it returns a RecommendationResponse with confidence="parse_error"
and the raw text preserved in `warnings`, so a caller always gets a valid
object to work with.
"""

import json
import re
from dataclasses import dataclass, field


@dataclass
class DirectRecommendation:
    standard_id: str
    reason: str
    status: str | None = None
    evidence_tag: str | None = None


@dataclass
class RelatedStandard:
    standard_id: str
    relationship: str
    related_to: str
    reason: str | None = None


@dataclass
class RecommendationResponse:
    query: str
    direct_recommendations: list[DirectRecommendation] = field(default_factory=list)
    related_standards: list[RelatedStandard] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: str = "unknown"  # "high" | "medium" | "low" | "insufficient_evidence" | "parse_error"


RESPONSE_FORMAT_INSTRUCTIONS = """
Respond with ONLY a single valid JSON object (no markdown fences, no commentary before or after) matching exactly this shape:

{
  "direct_recommendations": [
    {"standard_id": "<IS number, copied exactly from the evidence>", "status": "<current|withdrawn, from evidence>", "reason": "<why this standard applies, tied to specific evidence>", "evidence_tag": "<the [N] tag this came from>"}
  ],
  "related_standards": [
    {"standard_id": "<IS number>", "relationship": "<REFERENCES|REFERENCED_BY|REPLACED_BY|REPLACES, copied exactly from KNOWLEDGE GRAPH EVIDENCE>", "related_to": "<the standard_id it is related to>", "reason": "<short reason>"}
  ],
  "warnings": ["<any caveat: withdrawn status, insufficient evidence, ambiguous query, etc.>"],
  "confidence": "<one of: high, medium, low, insufficient_evidence>"
}

Every standard_id must be copied character-for-character from the evidence above - never invent one. If there are no direct recommendations, return an empty list and set confidence to "insufficient_evidence". Output nothing but the JSON object.
"""


def _extract_json_object(text: str) -> str:
    """Strip markdown code fences and surrounding prose some models add
    despite instructions, and isolate the outermost {...} object."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]
    return text


def parse_response(query: str, raw_text: str) -> RecommendationResponse:
    """Never raises. Malformed LLM output becomes a RecommendationResponse
    with confidence='parse_error' rather than crashing the pipeline."""
    try:
        candidate = _extract_json_object(raw_text)
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return RecommendationResponse(
            query=query,
            warnings=[f"LLM response was not valid JSON and could not be parsed: {raw_text[:500]!r}"],
            confidence="parse_error",
        )

    def _require_list(value, field_name: str) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"field {field_name!r} must be a list, got {type(value).__name__}")
        return value

    try:
        raw_direct = _require_list(data.get("direct_recommendations"), "direct_recommendations")
        raw_related = _require_list(data.get("related_standards"), "related_standards")
        raw_warnings = _require_list(data.get("warnings"), "warnings")

        direct = [
            DirectRecommendation(
                standard_id=str(item["standard_id"]),
                reason=str(item.get("reason", "")),
                status=item.get("status"),
                evidence_tag=item.get("evidence_tag"),
            )
            for item in raw_direct
            if isinstance(item, dict) and "standard_id" in item
        ]
        related = [
            RelatedStandard(
                standard_id=str(item["standard_id"]),
                relationship=str(item.get("relationship", "")),
                related_to=str(item.get("related_to", "")),
                reason=item.get("reason"),
            )
            for item in raw_related
            if isinstance(item, dict) and "standard_id" in item
        ]
        warnings = [str(w) for w in raw_warnings]
        confidence = str(data.get("confidence", "unknown"))
    except (KeyError, TypeError, ValueError) as e:
        return RecommendationResponse(
            query=query,
            warnings=[f"LLM JSON was valid but did not match the expected schema: {e}"],
            confidence="parse_error",
        )

    return RecommendationResponse(
        query=query,
        direct_recommendations=direct,
        related_standards=related,
        warnings=warnings,
        confidence=confidence,
    )
