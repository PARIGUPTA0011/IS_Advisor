"""
Builds the (system_prompt, user_message) pair sent to the LLM. The grounding
rules here are what Checkpoint 7's validator will later enforce in code -
the prompt asks nicely, the validator checks for real.
"""

from rag.context_builder import ContextBundle
from rag.metadata_store import MetadataStore
from rag.response_parser import RESPONSE_FORMAT_INSTRUCTIONS

SYSTEM_PROMPT = """You are IS-Advisor, an assistant that recommends applicable Indian Standards (IS) for a procurement specification.

You will be given a user's procurement query followed by evidence in three sections:
- RETRIEVED EVIDENCE: standards found by semantic search, with relevance scores.
- KNOWLEDGE GRAPH EVIDENCE: relationships (REFERENCES, REFERENCED_BY, REPLACED_BY, REPLACES) connecting those standards to other standards.
- STANDARD METADATA: structured facts about each retrieved standard (department, committee, certification, status, etc.)

STRICT GROUNDING RULES:
1. Only recommend or mention an IS number that literally appears in the RETRIEVED EVIDENCE or KNOWLEDGE GRAPH EVIDENCE sections above. Never invent, guess, or recall an IS number from your own training knowledge, even if you believe it exists.
2. The evidence does NOT include clause- or section-level text. Never cite a specific clause, sub-clause, or section number of a standard - refer to the standard as a whole only.
3. Only state a relationship between two standards (e.g. "references", "replaced by") if that exact relationship literally appears in the KNOWLEDGE GRAPH EVIDENCE section. Never infer or invent one.
4. Clearly separate DIRECT RECOMMENDATIONS (standards from RETRIEVED EVIDENCE that plausibly match the query) from RELATED STANDARDS (standards surfaced only through KNOWLEDGE GRAPH EVIDENCE - e.g. references or replacements of a direct recommendation).
5. Every recommendation needs a short reason tied to specific evidence (title, score, metadata field, or KG relationship) - never assert relevance without pointing to why.
6. If the evidence is weak, ambiguous, or absent, say so explicitly instead of guessing. Saying "insufficient evidence" is always preferable to fabricating a recommendation.
7. If a standard's status is "withdrawn", say so, and point to its replacement if the replacement appears in the evidence (replaced_by_is metadata or a REPLACED_BY relationship). Do not silently recommend a withdrawn standard as if it were current.
""" + RESPONSE_FORMAT_INSTRUCTIONS


def build_prompt(
    bundle: ContextBundle,
    metadata_store: MetadataStore,
    language: str | None = None,
) -> tuple[str, str]:
    """Returns (system_prompt, user_message). user_message is the full
    context text - it already includes the user query at the top.

    `language` only affects the language of the LLM's own generated text
    (titles/reasons/warnings) - it never changes what evidence is grounded on,
    since IS numbers and KG relationship types are language-independent
    tokens either way.
    """
    system_prompt = SYSTEM_PROMPT
    if language and language.lower() not in ("en", "english"):
        system_prompt += (
            f"\n\nRespond in {language}: write every `reason`, `warnings` entry, and other "
            "free-text field in that language. Do not translate standard_id, relationship, "
            "or confidence values - those stay exactly as they appear in the evidence."
        )
    return system_prompt, bundle.to_prompt_text(metadata_store)
