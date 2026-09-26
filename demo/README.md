# IS-Advisor demo

Paste a tender or upload a PDF; get, for every line item, the applicable Indian Standards, whether
each is current, whether it needs mandatory certification, and which other standards it
normatively requires. **Fully offline: no LLM, no API key, no network.**

```bash
python demo/server.py            # then open http://localhost:8765
```

Startup loads the embedding model and the graph once (20–60 s on CPU). After that, a full tender
takes about 4 seconds. "Load sample tender" runs a 16-line example that exercises every path.

## What happens to a tender

```
tender text / PDF
  │
  ▼  Semantic_Analysis/is_advisor          split into line items, strip boilerplate and citations,
  │                                        repair run-together PDF text, hybrid retrieval
  │  ranked kys_ids per line item          ← the contract in CLAUDE.md section 6
  ▼  rag.kg_client.get_kg_client()         Neo4j if reachable, else the same graph from CSV
  │  NORMATIVELY_REFERENCES, REPLACED_BY, REFERENCES per candidate
  ▼  demo/advisor.py                       version, reaffirmation, certification, QCO;
  │                                        withdrawn citations followed to their current replacement
  ▼
demo/static/index.html
```

## What the page shows, and where each fact comes from

| On the page | Source |
|---|---|
| Candidate standards and tier | semantic search (`Semantic_Analysis/`), tiers fitted in its README section 7 |
| "Current · 2008 edition · reaffirmed 2023" | `standards.csv`: `is_year`, `reaffirmed_year`; "≥" when the year comes from a BSB Edge preview, which is a lower bound |
| "Mandatory BIS certification", "QCO" | `standards.csv`: `mandatory_cert`, `qco_status`, `qco_date` |
| Normative references, and "withdrawn → use …" | knowledge graph `NORMATIVELY_REFERENCES` (clause 2), then `REPLACED_BY` followed to a current standard |
| "Cited IS 2062 is withdrawn. Current replacement: …" | citations found in the line, resolved against every standard including withdrawn ones |

## Knowledge graph backend

`KG_BACKEND=local` (the demo default) reads `IS_Standards_Data/edges.csv`, `standards.csv` and
`Semantic_Analysis/data/normative_refs_edges.csv` with the same rules as `Knowlege_Graph/04, 05, 07`,
so it holds the same edges Neo4j does: 160,266 REFERENCES, 6,113 REPLACED_BY and 35,896
NORMATIVELY_REFERENCES. Set `KG_BACKEND=auto` to use Neo4j when `.env` has credentials and it is
reachable, or `KG_BACKEND=neo4j` to require it.

## Known limits a judge may hit

- Real tender lines find the right standard in the top 5 about 59% of the time (86-item real-tender
  set, `Semantic_Analysis/README.md` section 7). A hand-written set says 92%; the lower number is
  the honest one.
- A withdrawn standard with no replacement recorded in the BIS data (IS 8112, merged into IS 269)
  is flagged as withdrawn, but no successor is shown. The data does not say, so the demo does not
  guess.
- Scanned PDFs are refused with a message, not searched as empty text.
