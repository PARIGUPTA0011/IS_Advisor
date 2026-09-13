# IS-Advisor — Frontend

React + TypeScript + Vite client for IS-Advisor. Talks to the FastAPI backend in `../api/main.py` over HTTP — no mocked data anywhere; every screen reflects what `/recommend` and `/health` actually return.

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_BASE_URL if the backend isn't on localhost:8000
npm run dev
```

The backend must be running separately (`python -m uvicorn api.main:app --port 8000` from the repo root) with `CORS_ALLOWED_ORIGINS` covering this dev server's origin (defaults already include `http://localhost:5173`).

## Structure

```
src/
  api/          fetch wrapper + typed calls (analysis.ts, health.ts)
  types/api.ts  mirrors api/main.py's Pydantic models exactly
  hooks/        useRecommend, useHealth - loading/success/error state around the API calls
  contexts/     ThemeContext (light/dark/system, persisted), AnalysisPrefsContext (top_k)
  i18n/         react-i18next config + en.json / hi.json
  components/
    layout/     sidebar, header, theme + language switchers
    analyze/    query textarea, upload dropzone, progress indicator
    results/    recommendation cards, evidence grid, related-standards chips, warnings
    common/     badges, skeletons, empty/error states
  pages/        Dashboard, Analyze, Results, Settings
```

## What's real vs. deferred

Built against confirmed backend capability only (see `../rag/README.md` and the Checkpoint 0 audit in project history for the full reasoning):

- **Dashboard, Analyze (text + file upload), Results, Settings** — fully real, backed by `/recommend`, `/recommend/document`, `/health`.
- **Tender Audit / Specification Health Score, Standards Explorer, Knowledge Graph explorer, Analysis History, Analytics** — intentionally not built. No backend scoring logic, browse endpoint, graph-traversal endpoint, or persistence layer exists yet for these; building them in the frontend would mean fabricating data, which this project explicitly avoids.

## Scripts

- `npm run dev` — dev server (Vite, default port 5173)
- `npm run build` — type-check (`tsc -b`) + production build
- `npm run lint` — oxlint
- `npm run preview` — preview the production build locally
