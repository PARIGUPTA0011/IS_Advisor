"""
Translates a non-English query to English before it reaches the retriever.

The semantic search index (Semantic_Analysis/) is built entirely from English
standard titles - BM25 and the bge-small-en-v1.5 embeddings are both
English-only. A Hindi query against that index would get near-zero keyword
overlap and poor embedding alignment (see rag/README.md's multilingual
discussion). Rather than rebuilding the index for every language, the query
itself is translated to English right before retrieval; the index and every
other pipeline stage stay untouched.

Scope: only Hindi is handled for now, per the current frontend's supported
languages (src/i18n/index.ts). Add more source languages by extending
SUPPORTED_SOURCE_LANGUAGES - no other code needs to change.
"""

from rag.llm_client import LLMClient

SUPPORTED_SOURCE_LANGUAGES = {"hindi", "hi"}

_TRANSLATE_SYSTEM_PROMPT = (
    "You are a translator for a procurement/technical-standards search system. "
    "Translate the user's Hindi text into English, preserving technical terms, "
    "units, and numbers exactly (e.g. \"90W\", \"IP66\", \"230V AC\"). "
    "Output ONLY the English translation - no quotes, no preamble, no explanation."
)


def needs_translation(language: str | None) -> bool:
    return bool(language) and language.strip().lower() in SUPPORTED_SOURCE_LANGUAGES


def translate_to_english(query: str, llm_client: LLMClient) -> str:
    """Best-effort translation via the LLM already configured for this pipeline
    (no separate translation API/key). Falls back to the original query on any
    failure - a translation hiccup should degrade retrieval quality, not crash
    the request."""
    try:
        translated = llm_client.generate(_TRANSLATE_SYSTEM_PROMPT, query, json_mode=False)
        translated = translated.strip()
        return translated or query
    except Exception:
        return query
