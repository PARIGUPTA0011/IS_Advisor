# IS_Advisor

AI-powered engine for identifying applicable **Indian Standards (IS)** for procurement specifications.

Describe a requirement or upload a tender PDF to get **grounded, explainable, and cited standard recommendations**.

### How it works

```text
Tender / Procurement Description
   (typed, PDF, or dictated)
            ↓
Speech → Text  (optional, local)
            ↓
PDF Requirement Extraction
            ↓
Hybrid Semantic Search
     (BM25 + Embeddings)
            ↓
Knowledge Graph Expansion
            ↓
Grounded RAG + LLM
            ↓
Grounding Validation
            ↓
Explainable IS Recommendations

```
Tech Stack

Frontend: React, TypeScript, Vite
Backend: Python, FastAPI, PyMuPDF
AI: RAG, BM25, Dense Embeddings, LLM
Knowledge Graph: Neo4j
Dataset: 35,524+ Indian Standards

Structure
IS_Standards_Data/ — Standards dataset
Semantic_Analysis/ — Hybrid retrieval
Knowlege_Graph/ — Neo4j knowledge graph
multilingual/ — language detection, translation, localised answers
speech/ — dictated input (faster-whisper, offline)
rag/ — RAG + grounding validation
api/ — FastAPI backend
frontend/ — React frontend
tests/ — Pipeline tests
Run
pip install -r requirements.txt
python -m uvicorn api.main:app --reload --port 8000

In another terminal:

cd frontend
npm install
npm run dev

### Asking by voice

```
python run_query.py --audio query.m4a     # wav/mp3/m4a, transcribed locally
python run_query.py --mic 8               # record 8 seconds and ask that
python Semantic_Analysis/03_search.py --audio spec.wav
```

Transcription runs on the machine (faster-whisper `small`, ~484 MB downloaded
once) - no API key, nothing uploaded. The transcript is printed before the
results so you can see what was heard, and a dictated `"आई एस सत्रह सौ छियासी"`
is rewritten to `IS 1786` before retrieval sees it.

**No transcription accuracy has been measured**, in any language. See
`speech/README.md` for what is supported, what is not, and the two dependency
pins that are load-bearing.
