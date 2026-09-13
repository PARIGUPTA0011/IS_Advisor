"""
FastAPI integration for the RAG pipeline. No backend existed in the repo
before this (Checkpoint 0), so this is new - additive only, nothing to
avoid breaking.

Run locally:
    python -m uvicorn api.main:app --reload --port 8000

Then:
    curl -X POST http://localhost:8000/recommend -H "Content-Type: application/json" \
         -d '{"query": "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."}'
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
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
    yield
    app_state["kg"].close()


app = FastAPI(title="IS-Advisor RAG API", lifespan=lifespan)


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 10


class RecommendationOut(BaseModel):
    standard_id: str
    status: str | None = None
    reason: str
    evidence_tag: str | None = None


class RelatedStandardOut(BaseModel):
    standard_id: str
    relationship: str
    related_to: str
    reason: str | None = None


class RecommendResponse(BaseModel):
    query: str
    recommendations: list[RecommendationOut]
    related_standards: list[RelatedStandardOut]
    warnings: list[str]
    confidence: str


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    result = run_query(
        query=req.query,
        retriever=app_state["retriever"],
        metadata_store=app_state["store"],
        kg_client=app_state["kg"],
        llm_client=app_state["llm"],
        top_k=req.top_k,
    )
    response = result.response
    return RecommendResponse(
        query=response.query,
        recommendations=[
            RecommendationOut(
                standard_id=r.standard_id, status=r.status, reason=r.reason, evidence_tag=r.evidence_tag
            )
            for r in response.direct_recommendations
        ],
        related_standards=[
            RelatedStandardOut(
                standard_id=r.standard_id, relationship=r.relationship, related_to=r.related_to, reason=r.reason
            )
            for r in response.related_standards
        ],
        warnings=response.warnings,
        confidence=response.confidence,
    )


@app.get("/health")
def health() -> dict:
    store: MetadataStore | None = app_state.get("store")
    return {"status": "ok", "standards_loaded": len(store) if store else 0}
