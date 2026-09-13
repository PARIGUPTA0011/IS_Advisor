# RAG Pipeline — IS Advisor

## TL;DR

Given a free-text procurement spec (e.g. *"LED street lights, 90W, 230V AC, outdoor use, IP66"*), this pipeline retrieves candidate Indian Standards, expands them with their Knowledge Graph relationships (references, replacements), hands all of it to an LLM as strict grounding context, and returns a structured recommendation — every claim traceable back to real evidence, with anything the LLM can't support automatically stripped out before it reaches the caller.

It is exposed as a FastAPI endpoint (`POST /recommend`) and is working end-to-end against **real semantic search** — `rag/retriever_factory.py` now wires in `SemanticRetriever` (`rag/semantic_retriever.py`), a hybrid BM25 + dense retriever built in `Semantic_Analysis/` (see that folder's own README for the full retrieval design, evaluation numbers, and known limits). `mock_retriever.py` still exists but is no longer used by default — see [What's real vs. what's a placeholder](#whats-real-vs-what-was-a-placeholder) below for exactly what's live versus what still needs a local build step.

---

## Architecture

```
query
  │
  ▼
Retriever.retrieve(query, top_k)          ← SEMANTIC SEARCH — SemanticRetriever, hybrid BM25 + dense (Semantic_Analysis/)
  │  list[{kys_id, score, ...}]
  ▼
hydrate()                                  rag/pipeline.py + rag/metadata_store.py
  │  looks up each kys_id in standards.jsonl → full Evidence(record=StandardRecord, ...)
  ▼
expand_with_kg()                           rag/pipeline.py + rag/kg_client.py
  │  Neo4j lookup per kys_id → REFERENCES / REFERENCED_BY / REPLACED_BY / REPLACES
  ▼
build_context()                            rag/context_builder.py
  │  assembles a tagged, deterministic evidence block ([1], [2], ... reused everywhere)
  ▼
build_prompt()                             rag/prompt_builder.py
  │  system prompt with strict grounding rules + the context as the user message
  ▼
LLMClient.generate()                       rag/llm_client.py
  │  Together AI (default) or Anthropic, JSON mode
  ▼
parse_response()                           rag/response_parser.py
  │  raw LLM text → RecommendationResponse (never raises, even on garbage output)
  ▼
validate()                                 rag/grounding_validator.py
  │  strips any recommendation/relationship not actually backed by the evidence
  ▼
PipelineResult                             returned by rag/pipeline.py::run_query()
```

All of this is orchestrated by **`rag/pipeline.py::run_query()`**, which is the one function that ties every stage together and is what `api/main.py` calls per request.

### Module-by-module

| File | Responsibility |
|---|---|
| `retriever_interface.py` | The contract between semantic search and everything else. Defines `RetrievedEvidence` (only `kys_id: int` and `score: float` are required) and the `Retriever` protocol. **Nothing downstream depends on how retrieval works — only on this shape.** |
| `retriever_factory.py` | **The single swap point.** `get_retriever()` now returns `SemanticRetriever`. This was the only file the semantic-search teammate needed to edit to plug in the real retriever. |
| `semantic_retriever.py` | Adapter from the `Semantic_Analysis/` hybrid retriever to the RAG `Retriever` protocol — converts its `Candidate` objects into `RetrievedEvidence` (`kys_id` + `score`), nothing more. |
| `mock_retriever.py` | Superseded, kept for reference/tests. Naive keyword/token-overlap scoring over standard titles — this is what stood in for semantic search before `SemanticRetriever` landed. |
| `schemas.py` | Core dataclasses: `StandardRecord` (hydrated metadata), `RelatedStandard` (one KG neighbor), `Evidence` (retrieval result + metadata + KG relations, combined). Field names match exactly what exists in `standards.jsonl`/`standards.csv` — nothing invented. |
| `metadata_store.py` | Loads all 35,524 records from `IS_Standards_Data/standards.jsonl` into memory once, keyed by `kys_id` (and `is_number`). This is what turns a bare `(kys_id, score)` into a full `StandardRecord`. |
| `kg_client.py` | `Neo4jKGClient` — queries the existing Neo4j graph (built by `Knowlege_Graph/02-06`, schema in `Knowlege_Graph/KG.md`) for `REFERENCES`/`REFERENCED_BY`/`REPLACED_BY`/`REPLACES` edges of a given `kys_id`. One Cypher query per lookup, using scoped `CALL` subqueries to avoid a cartesian blow-up on standards with many edges. |
| `context_builder.py` | Turns a list of `Evidence` into the exact text block sent to the LLM, in three sections: `RETRIEVED EVIDENCE`, `KNOWLEDGE GRAPH EVIDENCE`, `STANDARD METADATA`. Every item gets a stable `[N]` tag reused across all three sections and later by the grounding validator. KG relations are capped at 5 per (standard, relationship type) to avoid bloating the prompt for standards with 30+ edges. |
| `prompt_builder.py` | The system prompt. Encodes the grounding rules in plain language (only cite what's in evidence, no clause-level citations since none exist in the data, separate direct recommendations from KG-surfaced related standards, flag withdrawn standards, say "insufficient evidence" rather than guess). |
| `llm_client.py` | `LLMClient` protocol with two implementations: `TogetherLLMClient` (default, `Llama-3.3-70B-Instruct-Turbo`) and `AnthropicLLMClient`. Selected via `LLM_PROVIDER` env var. No hardcoded keys — each reads its own env var. |
| `response_parser.py` | Parses the LLM's raw text into a `RecommendationResponse` (dataclasses: `DirectRecommendation`, `RelatedStandard`, plus `warnings`/`confidence`). **Never raises** — malformed JSON or a schema mismatch becomes `confidence="parse_error"` with the raw text preserved, not a crash. |
| `grounding_validator.py` | The enforcement layer. The prompt *asks* the LLM to only cite supplied evidence; this module *checks* that it actually did, and rejects (never silently drops) anything that doesn't hold up: an unlisted `standard_id`, a fabricated clause/section citation, or a claimed KG relationship that doesn't exist in the actual graph evidence attached to this query. |
| `pipeline.py` | `hydrate()`, `expand_with_kg()`, and `run_query()` — the end-to-end orchestrator. Includes a **no-evidence short circuit**: if retrieval returns nothing, the LLM is never called at all (there'd be nothing to ground on, and calling it anyway risks the model falling back on its own training knowledge). Grounding is *enforced*, not just measured — rejected items are stripped from the response before it's returned. |

### Why the dataset shape drove these design choices

`IS_Standards_Data/standards.jsonl` / `standards.csv` is **standard-level, not chunk-level** — one row per Indian Standard (35,524 total), with rich structured metadata (`status`, `department`, `committee`, `mandatory_cert`, `replaced_by_id`, etc.) but **no clause- or passage-level text**. This shaped several decisions:

- The retriever's job is deliberately minimal: return *which* standards are relevant and *how* relevant (`kys_id` + `score`). Everything else — title, status, department, certification — is re-hydrated by the RAG layer itself from `standards.jsonl`, keyed on `kys_id`. This means the RAG pipeline has **zero coupling** to whatever the retriever's internals look like (FAISS, Chroma, BM25, hybrid — doesn't matter).
- There's no `evidence: [...]` array of cited passages in the output schema (as a typical RAG brief might suggest), because there's no passage-level text to cite. Instead, `evidence_tag` links a recommendation back to its `[N]` marker in the context.
- The grounding validator explicitly **rejects any clause/section-number citation** unless it's literally part of the standard's own title/number (e.g. `IS 16107 (Part 2/Sec 2):2017` legitimately contains "Sec 2" as part of its identity, not a fabricated internal citation) — because there is no legitimate way for the LLM to have supported clause-level data.

---

## What's real vs. what's a placeholder

| Component | Status |
|---|---|
| `metadata_store.py` | ✅ Real — loads and serves all 35,524 real standards |
| `kg_client.py` | ✅ Real — live-tested against a populated Neo4j Aura instance, cross-checked line-for-line against `edges.csv`/`standards.csv` |
| `context_builder.py`, `prompt_builder.py` | ✅ Real, fully tested |
| `llm_client.py` | ✅ Real — Together AI (`Llama-3.3-70B-Instruct-Turbo`, swappable via `LLM_MODEL`) or Anthropic |
| `response_parser.py`, `grounding_validator.py` | ✅ Real, tested including deliberately hallucinated/malformed inputs |
| `api/main.py` (FastAPI) | ✅ Real, tested via live HTTP calls |
| `semantic_retriever.py` / `Semantic_Analysis/` | ✅ Real — hybrid BM25 + dense retrieval, evaluated on a 121-item set (see `Semantic_Analysis/README.md` for full numbers and design). **Requires a local build step per machine** — see below. |
| `mock_retriever.py` | Superseded — kept only for reference/tests, no longer used by `retriever_factory.py`. |

Everything has been exercised against **live infrastructure** (a real, populated Neo4j Aura database and a real LLM API) or a real, measured retrieval evaluation — not mocked or simulated.

### Required local setup: building the semantic search index

`Semantic_Analysis/artifacts/` (the corpus, BM25 index, and embeddings) is **gitignored on purpose** — it's derived data, not source, so every machine that runs this pipeline has to build it locally once:

```
cd Semantic_Analysis
pip install -r ../requirements.txt
python 01_build_index.py              # full build with dense embeddings: 8-25 min on CPU
python 01_build_index.py --no-dense   # keyword-only (BM25) build: ~8 seconds
```

Without this step, `SemanticRetriever()` fails immediately (`pd.read_parquet` can't find `corpus.parquet`) — that's expected on a fresh clone, not a bug. `--no-dense` alone is enough to get the pipeline fully working (keyword search alone already ranks correctly, verified below); the full build adds dense/embedding-based retrieval on top. See `Semantic_Analysis/README.md` section 1 ("If the pinned versions will not import") if `torch`/`transformers` fail to import — this is a known, documented Windows/CPU version conflict with a verified workaround.

---

## How the two workstreams connect (`retriever_interface.py`)

```python
class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedEvidence]: ...
```

`rag/semantic_retriever.py` adapts `Semantic_Analysis`'s `Candidate` objects into this shape — only `kys_id` (int) and `score` (float) cross the boundary. `Semantic_Analysis`'s much richer output (`why`, `tier`, `requirements`, `cited_standards` — see its README section 9) is deliberately not used here, since the RAG layer re-derives everything else it needs from `standards.jsonl` by `kys_id`. This is what kept the two workstreams independently buildable: neither had to know the other's internals, only this one shared join key.

### Before/after: what the integration actually changed

**Concrete example** (query: `"LED street lights, 90W, 230V AC, outdoor use, IP66 protection."`):

With `MockRetriever` (naive keyword overlap), the top-5 retrieved standards were:
```
0.2828  IS 9421:1980   "Colours of indicator lights for shipboard use"      ← irrelevant
0.2582  IS 3682:1966   "Flameproof ac motors for use in mines"              ← irrelevant
0.2390  IS 7848:1975   "Studio spot lights for motion picture studios"     ← irrelevant
0.2390  IS 16107 ...   "LED Street Lighting Luminaire"                      ← the actual answer
0.2390  IS 19517 ...   "Sunglasses and Related Eyewear"                     ← irrelevant
```
The correct standard (`IS 16107 (Part 2/Sec 2):2017`) was tied for the *lowest* score, purely because of generic word overlap ("lights", "use").

With `SemanticRetriever` (keyword-only build, `--no-dense`), the same query now returns:
```
0.9536  IS 16107 (Part 2/Sec 2):2017  "LED Street Lighting Luminaire"       ← correct, ranked #1
0.9416  IS 16102 (Part 1):2026        "Self-Ballasted LED Lamps..."         ← genuinely related
0.9198  IS 10322 (Part 5/Sec 9):2017  "Luminaires... rope lights"
0.9095  IS 7848:1975                  "Studio spot lights..."
0.9009  IS 9421:1980                  "Colours of indicator lights..."
```
The LLM went on to recommend both `IS 16107` and `IS 16102`, plus three KG-verified `REFERENCES` relationships as related standards — none of that was reachable when the correct answer was buried in noise. This was run live, end-to-end, through `run_query.py`, not simulated.

---

## Environment setup

Copy `.env.example` to `.env` in the repo root and fill in:

```
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

LLM_PROVIDER=together          # or "anthropic"
TOGETHER_API_KEY=your-together-api-key
# ANTHROPIC_API_KEY=your-anthropic-api-key

# Optional overrides
# LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo
# LLM_MAX_TOKENS=4096
```

Install dependencies: `pip install -r requirements.txt` (from repo root).

**Never commit `.env`** — it's already gitignored. Only `.env.example` (placeholders) belongs in the repo.

---

## Running it

**One-off query from the command line:**
```
python run_query.py "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."
```

**As an API:**
```
python -m uvicorn api.main:app --reload --port 8000
```
```
curl -X POST http://localhost:8000/recommend \
     -H "Content-Type: application/json" \
     -d '{"query": "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."}'
```
`GET /health` reports how many standards loaded (`35524` when healthy) — useful to confirm the metadata store came up correctly under FastAPI.

**Test suite:** `tests/test_checkpoint2.py` through `test_checkpoint10.py` — each corresponds to one build checkpoint (retriever integration, KG expansion, context building, LLM generation, structured output, grounding validation, no-evidence handling, full integration). Run individually, e.g. `python tests/test_checkpoint7.py`.

---

## Known limitations / things worth knowing

- **No clause-level text.** The dataset has titles and structured metadata only — no passage/section text — so recommendations are grounded at the whole-standard level, never at a specific clause. This is a data limitation, not a pipeline gap.
- **`REPLACED_BY` direction matters for correctness, not for validation.** The grounding validator accepts a claimed relationship in either direction (`(A, REPLACED_BY, B)` or `(B, REPLACED_BY, A)`) since relationship phrasing direction isn't load-bearing for the accept/reject decision — but be careful when *displaying* results to users, since getting the arrow backwards (source vs. target) is a real, easy-to-make bug (it happened once during development, in a test script's print statement, not in the pipeline logic itself).
- **KG relations are capped at 5 per (standard, relationship type)** in the context sent to the LLM, with an explicit "...and N more not shown" note, to avoid bloating the prompt for standards with 30+ edges (some genuinely have this many `REFERENCES`).
- **The default LLM is Together AI's `Llama-3.3-70B-Instruct-Turbo`**, not Qwen3, because every Qwen3 variant on the currently configured Together account requires a paid dedicated endpoint (confirmed via live API testing — not a code or key issue). Switching models later is a one-line env var change (`LLM_MODEL=...`), no code change needed.
