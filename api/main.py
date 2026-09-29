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

import asyncio
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

# The repo root goes on the path before anything imports the model stack, so
# that quiet_warnings can install its filters first - see quiet_warnings.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiet_warnings  # noqa: E402

quiet_warnings.apply()

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel

from rag.kg_client import get_kg_client
from rag.llm_client import get_llm_client
from rag.metadata_store import MetadataStore
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever
from Semantic_Analysis.is_advisor.search import load_retriever
from api.tender_health import build_health_report

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
    app_state["health_retriever"] = load_retriever(
        with_dense=False,
        with_reranker=False,
        with_spacy=True,
    )
    # Neo4j when configured and reachable, the same graph from CSV otherwise,
    # so the API starts on a machine without Neo4j credentials.
    app_state["kg"] = get_kg_client()
    app_state["llm"] = get_llm_client()
    # Logged once at startup rather than as Neo4j notifications on every
    # request. An empty graph is a deployment problem, not a per-query one.
    warning = app_state["kg"].empty_graph_warning()
    if warning:
        print(f"! {warning}")

    # Translation is loaded lazily by design (multilingual/translate.py) so an
    # English-only deployment never pays for a 2.5GB model it does not need.
    # But that laziness meant the very FIRST non-English request after every
    # server start - or every --reload restart - paid the full load cost
    # inside that request's response time, on top of retrieval and the LLM
    # call. Measured on this machine: ~20s just for the model load, which can
    # push a request close to or past a client's timeout, and looks exactly
    # like "every non-English query is broken" if the developer is restarting
    # the server between attempts.
    #
    # Fired as a background task, started AFTER the server begins accepting
    # connections (not awaited here), so the app opens for English traffic
    # immediately and GET /health can genuinely report "loading" for the
    # ~20s this takes - rather than the alternative of blocking startup
    # entirely, which would make that state unobservable from outside.
    from multilingual.translate import warm_up as warm_up_translation
    from speech.transcribe import warm_up as warm_up_speech

    async def _background_warmup(name: str, fn) -> None:
        started = time.time()
        # warm_up() is blocking (CPU-bound, native-library); run it off the
        # event loop so requests and health checks remain responsive.
        await asyncio.to_thread(fn)
        print(f"[warmup] {name} warm-up task finished after {time.time() - started:.1f}s", flush=True)

    app_state["warmup_tasks"] = [
        asyncio.create_task(_background_warmup("translation", warm_up_translation)),
        asyncio.create_task(_background_warmup("speech", warm_up_speech)),
    ]

    yield
    for task in app_state["warmup_tasks"]:
        task.cancel()
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
    # Any of three spellings: a plain name as the frontend sends it ("Hindi",
    # "English"), an ISO code ("hi", "ta"), or a FLORES-200 code ("hin_Deva").
    # Omitted, the language is detected from the query. It sets the language of
    # the answer's free text; IS numbers, official titles and relationship names
    # always stay English.
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


class KnowledgeGraphNodeOut(BaseModel):
    id: str
    standard_id: str
    title: str | None = None
    status: str | None = None
    retrieved: bool


class KnowledgeGraphEdgeOut(BaseModel):
    source: str
    target: str
    relationship: str


class KnowledgeGraphOut(BaseModel):
    nodes: list[KnowledgeGraphNodeOut]
    edges: list[KnowledgeGraphEdgeOut]


class RecommendResponse(BaseModel):
    query: str                                   # as sent, in the caller's language
    recommendations: list[RecommendationOut]
    related_standards: list[RelatedStandardOut]
    evidence: list[EvidenceOut]
    knowledge_graph: KnowledgeGraphOut
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
    graph_nodes: dict[int, KnowledgeGraphNodeOut] = {}
    graph_edges: dict[tuple[int, int, str], KnowledgeGraphEdgeOut] = {}

    for evidence in result.evidence:
        if evidence.record:
            graph_nodes[evidence.kys_id] = KnowledgeGraphNodeOut(
                id=str(evidence.kys_id),
                standard_id=evidence.record.is_number,
                title=evidence.record.title,
                status=evidence.record.status,
                retrieved=True,
            )

    for evidence in result.evidence:
        if not evidence.record:
            continue
        for relation in evidence.kg_relations:
            related_record = app_state["store"].get(relation.kys_id)
            graph_nodes.setdefault(
                relation.kys_id,
                KnowledgeGraphNodeOut(
                    id=str(relation.kys_id),
                    standard_id=relation.is_number,
                    title=related_record.title if related_record else relation.title,
                    status=related_record.status if related_record else None,
                    retrieved=False,
                ),
            )
            source_id, target_id = evidence.kys_id, relation.kys_id
            if relation.relationship in {"REFERENCED_BY", "REPLACES"}:
                source_id, target_id = target_id, source_id
            graph_edges[(source_id, target_id, relation.relationship)] = KnowledgeGraphEdgeOut(
                source=str(source_id),
                target=str(target_id),
                relationship=relation.relationship,
            )

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
        knowledge_graph=KnowledgeGraphOut(
            nodes=list(graph_nodes.values()),
            edges=list(graph_edges.values()),
        ),
        warnings=response.warnings,
        confidence=response.confidence,
        query_english=response.query_english,
        language=response.language,
        warnings_localized=response.warnings_localized,
        unsupported_spec_terms=response.unsupported_spec_terms,
        detection=result.detection,
        translation=result.translation,
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

    from Semantic_Analysis.is_advisor.documents import ScannedPdfError, read_document

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


class TranscribeResponse(BaseModel):
    """Mirrors speech.transcribe.Transcript.to_dict(), plus two fields added for
    the frontend's convenience: `language_iso` and `language_name` resolve the
    FLORES code to what the language switcher already understands, so the
    frontend does not need to know FLORES codes to react to what was heard."""

    text: str
    raw_text: str
    language: str
    language_iso: str | None = None
    language_name: str | None = None
    whisper_language: str | None = None
    whisper_confidence: float | None = None
    detected_script: str
    detection_method: str
    language_mismatch: str
    duration: float | None = None
    notation_changes: list[list[str]] = []
    engine: str
    note: str


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = None,
) -> TranscribeResponse:
    """Speech in, transcript out - the speech/ edge layer, reachable over HTTP.

    Deliberately separate from /recommend: the frontend shows the transcript
    (and lets the user fix a misheard word) before spending a retrieval + LLM
    call on it, the same "print the transcript before the results" rule
    run_query.py and 03_search.py follow on the command line.

    `language` is optional and, if given, forces both what Whisper is told to
    expect and the language the transcript is reported in - the same override
    `--lang` gives the CLIs. Analyze.tsx currently omits it, so a dictated
    query is detected from the audio itself rather than assumed to match
    whatever the UI's current language happens to be.
    """
    from speech import SpeechUnavailable, transcribe_file
    from speech.config import SUPPORTED_AUDIO_SUFFIXES

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_AUDIO_SUFFIXES:
        # A browser MediaRecorder blob often has no real filename ("blob"), so
        # the suffix is inferred from the content type it declares instead of
        # rejecting audio the decoder can actually read.
        suffix = {
            "audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
            "audio/flac": ".flac",
        }.get((file.content_type or "").lower(), "")
        if suffix not in SUPPORTED_AUDIO_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported audio type. Use one of: {', '.join(SUPPORTED_AUDIO_SUFFIXES)}",
            )

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.")
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)
    try:
        transcript = transcribe_file(tmp_path, language=language)
    except SpeechUnavailable as error:
        # Not installed, or the model failed to load - a deployment problem,
        # not a bad request, so 503 rather than 400/422.
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        tmp_path.unlink(missing_ok=True)

    from multilingual import languages

    resolved = languages.resolve(transcript.language)
    payload = transcript.to_dict()
    return TranscribeResponse(
        **payload,
        language_iso=resolved.iso1 if resolved else None,
        language_name=resolved.name if resolved else None,
    )


@app.post("/tender-health")
async def tender_health(
    file: UploadFile = File(...),
) -> dict:
    """Audit an uploaded tender for cited and outdated Indian Standards."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="Only .pdf and .txt files are supported.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
        )
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    from Semantic_Analysis.is_advisor.documents import ScannedPdfError, read_document

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
        raise HTTPException(
            status_code=422,
            detail="No extractable text found in the uploaded file.",
        )

    results = app_state["health_retriever"].search_document(text)
    report = build_health_report(results)

    return {
        "total_items": report.total_items,
        "items_with_citations": report.items_with_citations,
        "items_without_citations": report.items_without_citations,
        "unique_standards_cited": report.unique_standards_cited,
        "current_standards": report.current_standards,
        "outdated_standards": report.outdated_standards,
        "standards": [
            {
                "cited_as": standard.cited_as,
                "is_number": standard.is_number,
                "title": standard.title,
                "status": standard.status,
                "replaced_by_is": standard.replaced_by_is,
                "successor_parts": standard.successor_parts,
                "note": standard.note,
            }
            for standard in report.standards
        ],
        "items_without_standards": report.items_without_standards,
    }


@app.get("/health")
def health() -> dict:
    from multilingual.translate import WARMUP_STATUS, get_translator
    from speech.transcribe import WARMUP_STATUS as SPEECH_WARMUP_STATUS

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
        # "not_started" | "loading" | "ready" | "failed" | "disabled" - the
        # frontend polls this to show "preparing language support" instead of
        # letting a non-English query race a cold model load. English queries
        # never consult this: multilingual.detect() short-circuits before
        # touching the translator at all for text that is already English.
        "warmup": WARMUP_STATUS,
        # Same idea, for the speech-to-text model (faster-whisper). Typed
        # queries never consult this.
        "speech_warmup": SPEECH_WARMUP_STATUS,
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
