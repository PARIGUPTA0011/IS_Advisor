"""
FastAPI integration for the RAG pipeline. No backend existed in the repo
before this (Checkpoint 0), so this is new - additive only, nothing to
avoid breaking.

Run locally:
    python -m uvicorn api.main:app --reload --port 8000

Then:
    curl -X POST http://localhost:8000/recommend -H "Content-Type: application/json" \
         -d '{"query": "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."}'

A query in any supported language is answered in that language. The language is
detected from the query unless the request names it:

    curl -X POST http://localhost:8000/recommend -H "Content-Type: application/json" \
         -d '{"query": "90W LED street light IP66", "language": "hi"}'

GET /languages lists what is supported and how translation is currently wired.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiet_warnings  # noqa: E402

quiet_warnings.apply()

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel

from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.metadata_store import MetadataStore
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever

app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Built once at startup - MetadataStore parses 35k+ records, and the KG
    # client holds a live Neo4j driver connection; neither should be
    # recreated per-request.
    store = MetadataStore()
    app_state["store"] = store
    app_state["retriever"] = get_retriever(store)
    app_state["kg"] = Neo4jKGClient.from_env()
    app_state["llm"] = get_llm_client()
    # Logged once at startup rather than as Neo4j notifications on every
    # request. An empty graph is a deployment problem, not a per-query one.
    warning = app_state["kg"].empty_graph_warning()
    if warning:
        print(f"! {warning}")
    yield
    app_state["kg"].close()


app = FastAPI(title="IS-Advisor RAG API", lifespan=lifespan)


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 10
    # ISO or FLORES-200 code ("hi", "ta", "hin_Deva"). Omitted, the language is
    # detected from the query and the answer comes back in it.
    language: str | None = None


class RecommendationOut(BaseModel):
    standard_id: str
    status: str | None = None
    reason: str
    evidence_tag: str | None = None
    # Localised text sits beside the English, never instead of it: standard_id
    # is an identifier and `reason` is what the grounding validator checked.
    reason_localized: str | None = None
    status_localized: str | None = None


class RelatedStandardOut(BaseModel):
    standard_id: str
    relationship: str
    related_to: str
    reason: str | None = None
    reason_localized: str | None = None
    title: str | None = None       # what this standard covers, from the dataset
    status: str | None = None      # "current" | "withdrawn"


class RecommendResponse(BaseModel):
    query: str                                   # as sent, in the caller's language
    recommendations: list[RecommendationOut]
    related_standards: list[RelatedStandardOut]
    warnings: list[str]
    confidence: str
    # All of these are null/empty for an English query, so an existing client
    # sees exactly the response it saw before.
    query_english: str | None = None             # what retrieval and the LLM saw
    language: dict | None = None                 # which language, and how it was decided
    warnings_localized: list[str] = []
    unsupported_spec_terms: list[str] = []
    detection: dict | None = None
    translation: dict | None = None


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    result = run_query(
        query=req.query,
        retriever=app_state["retriever"],
        metadata_store=app_state["store"],
        kg_client=app_state["kg"],
        llm_client=app_state["llm"],
        top_k=req.top_k,
        language=req.language,
    )
    response = result.response
    return RecommendResponse(
        query=response.query,
        recommendations=[
            RecommendationOut(
                standard_id=r.standard_id, status=r.status, reason=r.reason,
                evidence_tag=r.evidence_tag, reason_localized=r.reason_localized,
                status_localized=r.status_localized,
            )
            for r in response.direct_recommendations
        ],
        related_standards=[
            RelatedStandardOut(
                standard_id=r.standard_id, relationship=r.relationship,
                related_to=r.related_to, reason=r.reason,
                reason_localized=r.reason_localized,
                title=r.title, status=r.status,
            )
            for r in response.related_standards
        ],
        warnings=response.warnings,
        confidence=response.confidence,
        query_english=response.query_english,
        language=response.language,
        warnings_localized=response.warnings_localized,
        unsupported_spec_terms=response.unsupported_spec_terms,
        detection=result.detection,
        translation=result.translation,
    )


@app.get("/health")
def health() -> dict:
    from multilingual.translate import get_translator

    store: MetadataStore | None = app_state.get("store")
    # The translation status is in here rather than in a separate endpoint
    # because "which MT backends actually loaded" is exactly the kind of thing
    # that silently differs between machines: the IndicTrans2 checkpoints are
    # gated on HuggingFace, so a deployment without a token falls back to NLLB
    # and should be able to see that it did.
    kg = app_state.get("kg")
    graph: dict = {"available": False}
    if kg is not None:
        try:
            graph = {"available": True, **kg.describe_graph()}
        except Exception as error:
            graph = {"available": False, "error": f"{type(error).__name__}: {error}"}
    return {
        "status": "ok",
        "standards_loaded": len(store) if store else 0,
        "graph": graph,
        "translation": get_translator().status(),
    }


@app.get("/languages")
def supported_languages() -> dict:
    """What can be asked and answered, and how well.

    `first_class` is the 22 scheduled Indian languages plus English: script
    detection, curated glossary and label coverage, IndicTrans2 when it is
    available. `best_effort` is everything else the installed NLLB checkpoint
    carries - detected less reliably, with nothing hand-curated.
    """
    from multilingual import languages

    return {
        "first_class": [
            {
                "code": language.code, "name": language.name,
                "native_name": language.native_name, "script": language.script,
                "iso": language.iso1 or language.iso3,
            }
            for language in languages.ALL
            if language.tier == languages.TIER_FIRST_CLASS
        ],
        "best_effort": [
            {
                "code": language.code, "name": language.name,
                "native_name": language.native_name, "script": language.script,
                "iso": language.iso1 or language.iso3,
            }
            for language in languages.ALL
            if language.tier == languages.TIER_BEST_EFFORT
        ],
        "notes": [
            "IS numbers and official standard titles are never translated.",
            "Romanised input (for example \"TMT sariya chahiye\") is detected and "
            "searched as typed, because the curated trade names already match it.",
        ],
    }
