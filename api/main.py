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

import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.metadata_store import MetadataStore
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever

_SEMANTIC_ANALYSIS_ROOT = Path(__file__).resolve().parent.parent / "Semantic_Analysis"
if str(_SEMANTIC_ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEMANTIC_ANALYSIS_ROOT))

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

# Dev-friendly default (Vite's default port); override via CORS_ALLOWED_ORIGINS
# (comma-separated) for anything else, e.g. a deployed frontend origin.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB, matches the frontend's stated limit


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 10
    language: str | None = None  # e.g. "English", "Hindi" - affects only the LLM's generated text


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


class EvidenceOut(BaseModel):
    """Raw retrieval evidence, independent of what the LLM said about it -
    what a "why this applies" card shows. `tag` matches a recommendation's
    `evidence_tag` (e.g. both "[1]") so the frontend can link the two."""

    tag: str
    standard_id: str
    title: str | None = None
    status: str | None = None
    score: float
    why: str | None = None     # retriever's own match explanation, e.g. "matched: led, street, lighting"
    tier: str | None = None    # retriever's own relevance band, e.g. "Highly relevant"


class RecommendResponse(BaseModel):
    query: str
    recommendations: list[RecommendationOut]
    related_standards: list[RelatedStandardOut]
    evidence: list[EvidenceOut]
    warnings: list[str]
    confidence: str


def _run_and_build_response(query: str, top_k: int, language: str | None) -> RecommendResponse:
    result = run_query(
        query=query,
        retriever=app_state["retriever"],
        metadata_store=app_state["store"],
        kg_client=app_state["kg"],
        llm_client=app_state["llm"],
        top_k=top_k,
        language=language,
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
        evidence=[
            EvidenceOut(
                tag=f"[{i + 1}]",
                standard_id=e.record.is_number if e.record else f"<unknown kys_id={e.kys_id}>",
                title=e.record.title if e.record else None,
                status=e.record.status if e.record else None,
                score=e.score,
                why=e.why,
                tier=e.tier,
            )
            for i, e in enumerate(result.evidence)
        ],
        warnings=response.warnings,
        confidence=response.confidence,
    )


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest) -> RecommendResponse:
    return _run_and_build_response(req.query, req.top_k, req.language)


@app.post("/recommend/document", response_model=RecommendResponse)
async def recommend_document(
    file: UploadFile = File(...),
    top_k: int = 10,
    language: str | None = None,
) -> RecommendResponse:
    """Same pipeline as /recommend, but the query text comes from an uploaded
    file (.pdf or .txt) instead of being typed. Extraction reuses the existing,
    already-tested Semantic_Analysis/is_advisor/documents.py (pdfplumber) -
    no new PDF library. This treats the whole document as one query string;
    it does not yet do the richer per-line-item split that
    Semantic_Analysis.is_advisor.search.Retriever.search_document() supports."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.")
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    from is_advisor.documents import ScannedPdfError, read_document

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)
    try:
        text = read_document(tmp_path)
    except ScannedPdfError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    finally:
        tmp_path.unlink(missing_ok=True)

    if not text.strip():
        raise HTTPException(status_code=422, detail="No extractable text found in the uploaded file.")

    return _run_and_build_response(text, top_k, language)


@app.get("/health")
def health() -> dict:
    store: MetadataStore | None = app_state.get("store")
    return {"status": "ok", "standards_loaded": len(store) if store else 0}
