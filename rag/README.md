# RAG Pipeline — IS Advisor

## TL;DR

Given a free-text procurement spec (e.g. *"LED street lights, 90W, 230V AC, outdoor use, IP66"*), this pipeline retrieves candidate Indian Standards, expands them with their Knowledge Graph relationships (references, replacements), hands all of it to an LLM as strict grounding context, and returns a structured recommendation — every claim traceable back to real evidence, with anything the LLM can't support automatically stripped out before it reaches the caller.

It is exposed as a FastAPI endpoint (`POST /recommend`, plus `POST /recommend/document` for an uploaded PDF or text file) and is working end-to-end against **real semantic search** — `rag/retriever_factory.py` now wires in `SemanticRetriever` (`rag/semantic_retriever.py`), a hybrid BM25 + dense retriever built in `Semantic_Analysis/` (see that folder's own README for the full retrieval design, evaluation numbers and known limits). `mock_retriever.py` still exists but is no longer what runs. See [How the two workstreams connect](#how-the-two-workstreams-connect-retriever_interfacepy).

A query may arrive in any of the 22 scheduled Indian languages and the recommendation comes back in that language, with every IS number and official title left in English. See [Multilingual queries](#multilingual-queries) — and note the ordering there, because it is what keeps the grounding validator meaningful.

---

## Architecture

```
query (any supported language)
  │
  ▼
multilingual.prepare_query()               detect language → translate to English → glossary hints
  │  English query text from here on
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
  │  Groq / Ollama / any OpenAI-compatible endpoint / Together / Anthropic, JSON mode
  ▼
parse_response()                           rag/response_parser.py
  │  raw LLM text → RecommendationResponse (never raises, even on garbage output)
  ▼
validate()                                 rag/grounding_validator.py
  │  strips any recommendation/relationship not actually backed by the evidence
  ▼
localise_response()                        rag/pipeline.py + multilingual/localize.py
  │  translates reasons, statuses and warnings; never an IS number
  ▼
PipelineResult                             returned by rag/pipeline.py::run_query()
```

Everything between `prepare_query` and `localise_response` sees English and only English. That is
the whole design of the multilingual layer: retrieval, the knowledge graph, the prompt, the LLM and
the validator all run on exactly the English they were built and tested against.

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
| `llm_client.py` | `LLMClient` protocol with three implementations behind five `LLM_PROVIDER` values: `OpenAICompatibleLLMClient` (`groq`, `ollama`, `openai_compatible`), `TogetherLLMClient` (`together`) and `AnthropicLLMClient` (`anthropic`). No hardcoded keys — each reads its own env var. Env is resolved when a client is built, not at import. |
| `response_parser.py` | Parses the LLM's raw text into a `RecommendationResponse` (dataclasses: `DirectRecommendation`, `RelatedStandard`, plus `warnings`/`confidence`). **Never raises** — malformed JSON or a schema mismatch becomes `confidence="parse_error"` with the raw text preserved, not a crash. |
| `grounding_validator.py` | The enforcement layer. The prompt *asks* the LLM to only cite supplied evidence; this module *checks* that it actually did, and rejects (never silently drops) anything that doesn't hold up: an unlisted `standard_id`, a fabricated clause/section citation, or a claimed KG relationship that doesn't exist in the actual graph evidence attached to this query. |
| `semantic_retriever.py` | The adapter that satisfies `Retriever` by wrapping `Semantic_Analysis/is_advisor/search.py`. Maps its `Candidate` objects to `RetrievedEvidence`, keeping `kys_id` as the only join key. This is what `get_retriever()` returns. |
| `kg_editions.py` | Reduces each related-standard set to **one edition per standard** — the current, latest one, by the same rule the retrieval index uses — and annotates every survivor with its `status`. The graph holds every edition, so a single `REFERENCES` set legitimately contains both `IS 10322 (Part 5/Sec 3):2012` and `:2026`; showing both to a procurement officer is still wrong. A group with no current edition keeps its newest withdrawn one, marked, rather than vanishing. |
| `spec_coverage.py` | Computes which specification values in the query (`IP66`, `90W`, `DN 150`, `K9`) **no evidence line states**, and appends one caveat naming them. Deterministic: the same query and evidence give the same answer every time. It reuses the notation patterns from `multilingual/protect.py` rather than defining a second idea of what a spec token is. |
| `pipeline.py` | `hydrate()`, `expand_with_kg()`, `localise_response()`, and `run_query()` — the end-to-end orchestrator. Includes a **no-evidence short circuit**: if retrieval returns nothing, the LLM is never called at all (there'd be nothing to ground on, and calling it anyway risks the model falling back on its own training knowledge). Grounding is *enforced*, not just measured — rejected items are stripped from the response before it's returned. |

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
| `llm_client.py` | ✅ Real — Groq or Ollama (both free), any OpenAI-compatible endpoint, Together AI, or Anthropic. Provider selection and the request path are covered by `tests/test_llm_providers.py`, which runs with no key and no network |
| `response_parser.py`, `grounding_validator.py` | ✅ Real, tested including deliberately hallucinated/malformed inputs |
| `api/main.py` (FastAPI) | ✅ Real, tested via live HTTP calls |
| `semantic_retriever.py` / `Semantic_Analysis/` | ✅ Real — hybrid BM25 + dense retrieval, evaluated on a 121-item set (see `Semantic_Analysis/README.md` for full numbers and design). This is what `get_retriever()` returns. |
| `multilingual/` (shared) | ✅ Real — detection and localisation are covered by `tests/test_multilingual.py`, which runs without the translation checkpoints. The better translation model is gated; see [Multilingual queries](#multilingual-queries). |
| `mock_retriever.py` | Superseded — kept as the fallback the pipeline was built against, and as the thing the checkpoint tests can run without an index. Not what runs. |

Everything has been exercised against **live infrastructure** (a real, populated Neo4j Aura database and a real LLM API) or a real, measured retrieval evaluation — not mocked or simulated.

### The search index is committed, not built per machine

`Semantic_Analysis/artifacts/` (corpus, BM25 index, embeddings — about 55 MB) is **committed on purpose**, so a fresh clone can run immediately instead of waiting up to 25 minutes for `01_build_index.py`. That is a deliberate trade for demo reliability, and `.gitignore` carries the reasoning next to the negation that keeps those files trackable.

What that buys you: nothing to build after a clone. What it costs: the index has to be **rebuilt and recommitted** when either input changes —

```
cd Semantic_Analysis
python 01_build_index.py              # full build with dense embeddings: 8-25 min on CPU
python 01_build_index.py --no-dense   # keyword-only (BM25) build: ~8 seconds
```

— and those inputs are `IS_Standards_Data/standards.csv` and the `BI_ENCODER` named in `is_advisor/config.py`. Forget to recommit and it fails *quietly rather than loudly*: `load_retriever()` compares the stored text fingerprint **and** the encoder name in `index_meta.json`, warns on stderr, and drops to keyword-only rather than silently comparing a query vector against vectors from a different model. That guard is what caught an English index being merged in under a multilingual config.

If `torch`/`transformers` fail to import, see `Semantic_Analysis/README.md` section 1 ("If the pinned versions will not import") — a known Windows/CPU version conflict with a verified workaround, and the reason `requirements.txt` pins the older stack.

---

## How the two workstreams connect (`retriever_interface.py`)

```python
class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievedEvidence]: ...
```

`rag/semantic_retriever.py` adapts `Semantic_Analysis`'s `Candidate` objects into this shape. Only `kys_id` (int) and `score` (float) are required to cross the boundary — that's the one hard coupling point, and it's what kept the two workstreams independently buildable. Two more fields ride along as optional, presentation-only passengers: `why` (the retriever's own match explanation, e.g. `"matched: led, street; semantically similar title; product specification"`) and `tier` (`"Highly relevant"` / `"Related"` / `"Possibly relevant"`) — both flow untouched through `Evidence` (`schemas.py`) and out through `/recommend`'s `evidence` array, for a frontend "why this applies" card. Nothing else from `Semantic_Analysis`'s richer output (`requirements`, `cited_standards` — see its README section 9) crosses this boundary; the RAG layer re-derives everything else it needs from `standards.jsonl` by `kys_id` instead.

### Before/after: what the integration actually changed

**Concrete example** (query: `"LED street lights, 90W, 230V AC, outdoor use, IP66 protection."`):

### How it is wired

`rag/semantic_retriever.py` puts `Semantic_Analysis/` on `sys.path`, calls `is_advisor.search.load_retriever()` once, and maps each `Candidate` to a `RetrievedEvidence` — `kys_id` and `score` are load-bearing, `matched_text` and `is_number` are carried for traceability only. `hydrate()`, KG expansion, context building, grounding validation and the FastAPI layer depend only on `kys_id` and the `Retriever` protocol, never on retriever internals, so nothing else changed.

The retriever owns its own persisted index, which is why `get_retriever()` discards the `metadata_store` it is handed: the corpus lives in `Semantic_Analysis/artifacts/`, and the RAG layer re-hydrates metadata from `standards.jsonl` itself.

### What "done" looks like

Run `python run_query.py "<some query>"` (from the repo root) before and after the swap. Before: top-5 results are frequently keyword-noise (see the LED-street-light example below). After: the correct standard(s) should rank clearly at the top, and `RELATED STANDARDS` should start surfacing more consistently since KG expansion works off whatever the retriever finds first.

**Concrete before/after example** (query: `"LED street lights, 90W, 230V AC, outdoor use, IP66 protection."`):

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

## What the related-standards list guarantees

Three things are now decided in code rather than left to the model, because each of them was observably unreliable when it was not.

**One edition per standard.** `kg_editions.py`, applied inside `expand_with_kg()`. `status == "current" AND is_canonical`, then the highest `is_year`, tie-broken on the higher `kys_id` — deliberately identical to `Semantic_Analysis/is_advisor/corpus.py::select_index_rows`, so retrieval and the graph agree on what "current edition" means. Withdrawn editions that survive (because nothing current exists for that base standard) are marked `[WITHDRAWN]` in the CLI and carry `status` in the API.

**What each standard covers.** Every related standard carries a `title` and `status` taken from the metadata store after validation — never from the model. So even a lazy `reason` sits next to the standard's real subject:

```
- IS 2906:1984 --REPLACES--> IS 14846:2000 [WITHDRAWN]
  covers: Sluice Valves for Water Works Purposes (350 to 1200 mm Size) (Withdrawn)
  reason: Was the earlier standard for sluice valves (350-1200 mm) now withdrawn and replaced by IS 14846
```

The prompt also now forbids reusing one sentence across entries and asks for what the standard covers rather than a restatement of the edge — the response schema previously asked for `"<short reason>"`, which is exactly what it got: the same generic line for every entry.

**Values the evidence cannot confirm.** `spec_coverage.py`. This replaced a caveat that depended on the model remembering it: one run warned that `IP66` was not covered and the next, on the identical query, did not — and a caveat that appears at random is worse than none, because its absence reads as confirmation. Now:

```
SPEC VALUES NOT CONFIRMED BY EVIDENCE: DN 150, K9
```

plus one sentence in `warnings`, and `unsupported_spec_terms` on the API response. Bare numbers and IS citations are excluded (a bare `100` claims nothing; a citation is resolved separately). Prompt rule 9 now tells the model *not* to add its own version, so there is one source for it.

It fires on most queries carrying a value, and that is correct rather than noisy: `Semantic_Analysis/README.md` section 4 measures numeric specifications as appearing in 1.6% of indexed titles. The dataset has no clause text, so "the standard probably specifies IP66" is not something this evidence can support. The wording says the standards are recommended on scope, not that they fail to comply — conflating "not evidenced" with "not compliant" would be its own kind of wrong.

## Multilingual queries

A query in any of the 22 scheduled Indian languages is answered in that language. The layer lives in the repo-root `multilingual/` package, shared with the retrieval workstream, and `multilingual/README.md` is its reference.

**The ordering is the design, and it is not negotiable.** Translation into English happens before retrieval; translation out of English happens *after* `grounding_validator.py` has run. The validator rejects a claim by matching IS numbers and clause patterns in the model's own prose (`_CLAUSE_PATTERN`, `retrieved_ids`), and it cannot do that in a language it was not written for. Translating before it ran would mean validating nothing while appearing to validate everything — so every stage that decides correctness sees English, and only what is displayed is translated.

Three consequences worth stating plainly:

- **The LLM is prompted in English and answers in English.** The evidence block is English, and a model asked to reason in one language about evidence in another paraphrases instead of citing. The translation of its `reason` text happens afterwards, locally.
- **`standard_id` and `relationship` are never translated.** The first is an identifier; the second (`REFERENCES`, `REPLACED_BY`) is matched against the knowledge graph's own labels.
- **Localised fields are additive.** For an English query, `language`, `query_english`, `warnings_localized` and every `*_localized` field are null or empty, so an existing client sees exactly the response it saw before.

### Request and response

```bash
curl -X POST http://localhost:8000/recommend \
     -H "Content-Type: application/json" \
     -d '{"query": "90W LED street light IP66", "language": "hi"}'
```

`language` is optional — omitted, it is detected from the query. Sending it forces both directions, which is also how to ask in English and read the answer in another language.

The response gains `query_english` (what retrieval and the LLM actually saw), `language` (which language, and how it was decided), `warnings_localized`, `detection`, `translation`, and `reason_localized` / `status_localized` on each recommendation.

`GET /languages` lists what is supported, split into `first_class` (the 22 scheduled languages plus English: script detection, curated glossary and labels) and `best_effort` (whatever else the installed NLLB checkpoint carries). `GET /health` now also reports which translation backends actually loaded — worth checking, because **the IndicTrans2 checkpoints are gated on HuggingFace**. Without `HF_TOKEN` and the model terms accepted, the layer falls back to `facebook/nllb-200-distilled-600M` (~2.5 GB, ungated), which is what a fresh install will be running.

```bash
python run_query.py "90W LED street light IP66" --lang hi
python run_query.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D"
```

---

## Choosing an LLM provider

Five values of `LLM_PROVIDER`, three client classes. **Two of them are free**, which is the point: nothing in this pipeline needs a paid provider.

| `LLM_PROVIDER` | Cost | Needs | Good for |
|---|---|---|---|
| `groq` | free tier, no card | a key from [console.groq.com/keys](https://console.groq.com/keys) | the default recommendation — a 70B model at speed |
| `ollama` | free | [Ollama](https://ollama.com) installed locally | offline work, no account at all |
| `openai_compatible` | depends | `LLM_BASE_URL` + `LLM_API_KEY` | llama.cpp, vLLM, LM Studio, OpenRouter, anything else speaking the OpenAI API |
| `together` | paid | `TOGETHER_API_KEY` | unchanged, still works |
| `anthropic` | paid | `ANTHROPIC_API_KEY` | unchanged, still works |

`groq` and `ollama` are the *same client* as `openai_compatible` with the base URL and a default model filled in. One SDK (`openai`) covers all three, so the free path needs no extra install beyond `requirements.txt`.

### Groq

```
LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_key_here
```

Default model `llama-3.3-70b-versatile` — a Groq **production** model on the free tier, and the same Llama 3.3 70B the Together default used, so the grounding behaviour measured for this pipeline carries over instead of having to be re-checked. `llama-3.1-8b-instant` is the faster, weaker alternative; `openai/gpt-oss-20b` and `openai/gpt-oss-120b` are also production models there. JSON object mode is available on all Groq models and requires the prompt to ask for JSON in words too, which `prompt_builder.py` already does.

### Ollama

```
ollama pull qwen2.5:3b
```
```
LLM_PROVIDER=ollama
LLM_API_KEY=ollama
```

The key is required by the OpenAI SDK and ignored by Ollama, so any placeholder works. Default model `qwen2.5:3b` (~1.9 GB), which answers on a CPU laptop; `llama3.2:3b` and `qwen3:1.7b` are lighter.

**Expect a real quality drop here, and know where it shows up.** A 3B model asked for strict JSON over a long evidence block will sometimes return malformed JSON (which becomes `confidence="parse_error"` with the raw text preserved, never a crash) and will more often make claims the grounding validator then rejects — so the visible symptom is fewer recommendations, not wrong ones. That is the pipeline working as designed: `grounding_validator.py` is what makes a weak local model safe to use at all. Use Ollama for offline development and Groq when the answer matters.

### Anything else

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-endpoint/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model-id
```

`LLM_MODEL` is required for an unknown endpoint — a guessed model id fails at request time with a much less obvious message than "set LLM_MODEL". A base URL that looks like Ollama (`:11434`) is recognised, so that case still needs neither a key nor a model.

**Not every OpenAI-compatible server implements `response_format`,** and the ones that don't reject the whole request rather than ignoring the field. So a rejected JSON-mode call is retried once without it, the result is remembered for the process, and the prompt's written JSON instructions carry it — `response_parser.py` never raises on non-JSON output.

## Environment setup

Copy `.env.example` to `.env` in the repo root and fill in the Neo4j block plus **one** of the provider blocks above:

```
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

LLM_PROVIDER=groq
LLM_API_KEY=gsk_your_groq_key_here

# Optional, any provider
# LLM_MODEL=llama-3.3-70b-versatile
# LLM_MAX_TOKENS=4096
```

Install dependencies: `pip install -r requirements.txt` (from repo root). `together` and `anthropic` are *not* in `requirements.txt` — install either only if you use that provider. `fastapi` and `uvicorn` now are: the API was documented here but never pinned, so a fresh install could run `run_query.py` and not the API.

Two third-party warnings (`clean_up_tokenization_spaces` from transformers, `TypedStorage` from torch) are filtered by `quiet_warnings.py`, called from the entry points only — applications get to set a warnings policy, libraries do not. Both filters match on message text, so a *new* warning from either library still gets through, and `IS_ADVISOR_ALL_WARNINGS=1` restores them.

**Never commit `.env`** — it's already gitignored. Only `.env.example` (placeholders) belongs in the repo.

One fix worth knowing about if you ever set `LLM_MODEL` and saw it ignored: this module used to read `LLM_MODEL` and `LLM_MAX_TOKENS` at **import** time, and `.env` was only loaded later, inside `Neo4jKGClient.from_env()` — which runs *after* `import rag.llm_client` in both `run_query.py` and `api/main.py`. So the `.env` value was silently discarded and the hardcoded default used. Both are now read when a client is constructed, and `get_llm_client()` calls `load_dotenv()` itself rather than depending on the knowledge-graph client having run first.

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
`GET /health` reports how many standards loaded (`35524` when healthy) — useful to confirm the metadata store came up correctly under FastAPI — plus which translation backends came up and a `graph` block with node and relationship counts.

### When the graph is empty

An empty or half-loaded Neo4j makes the server emit a notification for every missing label, property and relationship type, on **every query** — dozens of `Received notification from DBMS server` blocks that bury the result and all say the same thing. Those are now off at both ends: the server is asked not to raise them (`notifications_min_severity`) and the driver not to log them (`warn_notification_severity`). `NEO4J_NOTIFICATIONS=1` brings them back for debugging a Cypher change.

In their place, `Neo4jKGClient.empty_graph_warning()` prints one sentence, once, naming the scripts to run. `run_query.py` calls it at startup and `api/main.py` logs it on boot. This matters because an empty graph is otherwise **invisible**: every recommendation still comes back from retrieval, and only `related_standards` is silently `[]`.

`describe_graph()` is the underlying counter. On a correctly loaded graph:

| | count | source |
|---|---|---|
| `Standard` nodes | 35,524 | every row of `standards.csv` |
| `Department` / `Committee` / `Certification` nodes | 17 / 390 / 1 | distinct codes |
| `REFERENCES` | 160,266 | every row of `edges.csv` |
| `REPLACED_BY` | 6,113 | rows with a non-null `replaced_by_id` |
| `BELONGS_TO` / `MAINTAINED_BY` | 35,382 each | rows carrying both a department and a committee |
| `REQUIRES_CERTIFICATION` | 725 | rows with `mandatory_cert` |

237,868 relationships in total, which fits inside AuraDB Free's 400,000 limit (35,932 nodes against its 200,000).

**Create the constraints before loading.** Every build script does `MERGE`/`MATCH` on `Standard {kys_id}`, and `04_create_reference_relationships.py.py` does it 160,266 times — without an index that is a full node scan per row. One statement per label fixes it, and the uniqueness half also stops a re-run creating duplicate nodes:

```cypher
CREATE CONSTRAINT standard_kys_id IF NOT EXISTS FOR (s:Standard) REQUIRE s.kys_id IS UNIQUE;
CREATE CONSTRAINT department_code IF NOT EXISTS FOR (d:Department) REQUIRE d.code IS UNIQUE;
CREATE CONSTRAINT committee_code  IF NOT EXISTS FOR (c:Committee)  REQUIRE c.code IS UNIQUE;
CREATE CONSTRAINT certification_name IF NOT EXISTS FOR (c:Certification) REQUIRE c.name IS UNIQUE;
```

**Provider tests:** `python tests/test_llm_providers.py` — no key, no network. It checks that each `LLM_PROVIDER` resolves to the right base URL and model, that Ollama needs no key while Groq says so clearly when one is missing, that `LLM_MODEL` from the environment beats the preset, and that the JSON-mode retry works, by running a mock OpenAI-compatible server on localhost (which is exactly what Ollama looks like to this client).

**Edition tests:** `python tests/test_kg_editions.py` — no database. The two-editions case from a real run, status beating a newer year, an all-withdrawn group being kept and marked, parts of one family staying separate, and the same standard under two relationship types appearing under both.

**Spec-coverage tests:** `python tests/test_spec_coverage.py` — no model. Extraction, exclusions (citations, bare numbers), separator-insensitive matching so `IP 66` covers `IP66`, and a determinism check that runs the same query 20 times and asserts one distinct result.

**Graph health tests:** `python tests/test_kg_health.py` — no database. Checks that an empty graph produces exactly one actionable message naming the build scripts, that a loaded graph produces none, and that an unreachable graph reports the connection error rather than claiming emptiness.

**Test suite:** `tests/test_checkpoint2.py` through `test_checkpoint10.py` — each corresponds to one build checkpoint (retriever integration, KG expansion, context building, LLM generation, structured output, grounding validation, no-evidence handling, full integration). Run individually, e.g. `python tests/test_checkpoint7.py`.

---

## Known limitations / things worth knowing

- **No clause-level text.** The dataset has titles and structured metadata only — no passage/section text — so recommendations are grounded at the whole-standard level, never at a specific clause. This is a data limitation, not a pipeline gap.
- **`REPLACED_BY` direction matters for correctness, not for validation.** The grounding validator accepts a claimed relationship in either direction (`(A, REPLACED_BY, B)` or `(B, REPLACED_BY, A)`) since relationship phrasing direction isn't load-bearing for the accept/reject decision — but be careful when *displaying* results to users, since getting the arrow backwards (source vs. target) is a real, easy-to-make bug (it happened once during development, in a test script's print statement, not in the pipeline logic itself).
- **KG relations are capped at 5 per (standard, relationship type)** in the context sent to the LLM, with an explicit "...and N more not shown" note, to avoid bloating the prompt for standards with 30+ edges (some genuinely have this many `REFERENCES`).
- **A non-English answer is machine translation, and it says so.** The corpus is English (33,803 of 35,524 rows), so a same-language answer is produced rather than looked up. The grounded English text is kept alongside every translated string, and the `language` block on the response records that the translation is machine-produced.
- **`LLM_PROVIDER` still defaults to `together`** for backwards compatibility, but nothing requires a paid provider any more: `groq` and `ollama` are both free, and an unconfigured checkout that falls through to the default now gets an error naming both instead of a missing-credentials failure from Together's SDK. Switching provider or model is an env var change, never a code change.
- **Together's model choice is `Llama-3.3-70B-Instruct-Turbo`**, not Qwen3, because every Qwen3 variant on the Together account used here requires a paid dedicated endpoint (confirmed via live API testing — not a code or key issue). The Groq default is the same Llama 3.3 70B, so the two are comparable.
