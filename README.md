# IS_Advisor

AI-powered engine for identifying applicable **Indian Standards (IS)** for procurement specifications.

Describe a requirement or upload a tender PDF to get **grounded, explainable, and cited standard recommendations**.

### How it works

```text
Tender / Procurement Description
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
