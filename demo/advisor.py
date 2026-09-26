"""Offline IS-Advisor: semantic search, then the knowledge graph, no LLM.

    from demo.advisor import Advisor
    result = Advisor().analyze(tender_text)

This is the product the problem statement describes, end to end, without a
network connection or an API key:

1. Semantic search (Semantic_Analysis/is_advisor) splits the tender into line
   items and ranks candidate standards for each one.
2. The knowledge graph (rag.kg_client: Neo4j when reachable, the same graph
   from CSV otherwise) expands every candidate: the standards it normatively
   references, what it replaced, and whether each of those is still current.
3. The metadata answers the version and certification questions directly:
   edition year, last reaffirmation and where that year came from, mandatory
   certification and QCO status.

The contract between 1 and 2 is the one agreed in CLAUDE.md section 6: search
ends at a ranked list of kys_ids, and the graph takes it from there.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "Semantic_Analysis"))

from rag.kg_client import (  # noqa: E402
    NORMATIVELY_REFERENCES,
    REFERENCED_BY,
    REFERENCES,
    REPLACED_BY,
    REPLACES,
    get_kg_client,
)

MAX_NORMATIVE = 12        # normative references listed per candidate
MAX_REPLACEMENT_HOPS = 5  # a withdrawn standard's successor can itself be withdrawn

_META_COLUMNS = [
    "kys_id", "is_number", "is_base_id", "is_year", "title_clean", "status", "aspect",
    "reaffirmed_year", "reaffirmed_year_source", "last_confirmed_year", "mandatory_cert",
    "certification", "qco_status", "qco_date", "replaced_by_id", "replaced_by_is",
    "dept_code", "committee", "ics",
]


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "n/a", "nan", "none"}:
        return None
    return value


class Advisor:
    def __init__(self, top_k: int = 5):
        from is_advisor.search import load_retriever

        self.top_k = top_k
        self.retriever = load_retriever(with_reranker=False)
        self.kg = get_kg_client()
        meta = pd.read_csv(REPO_ROOT / "IS_Standards_Data" / "standards.csv",
                           usecols=_META_COLUMNS, low_memory=False)
        self.meta = {int(r["kys_id"]): {k: _clean(v) for k, v in r.items()}
                     for r in meta.to_dict("records")}

    # ---------------- pieces ----------------

    def standard(self, kys_id: int) -> dict:
        """Version and certification facts for one standard."""
        m = self.meta.get(int(kys_id), {})
        year = m.get("is_year")
        reaffirmed = m.get("reaffirmed_year")
        return {
            "kys_id": int(kys_id),
            "is_number": m.get("is_number"),
            "title": m.get("title_clean"),
            "status": m.get("status"),
            "aspect": m.get("aspect"),
            "edition_year": int(year) if year else None,
            "reaffirmed_year": int(reaffirmed) if reaffirmed else None,
            # A preview year is a lower bound: reaffirmed at least this recently.
            "reaffirmed_year_is_lower_bound": m.get("reaffirmed_year_source") == "bsb_preview",
            "last_confirmed_year": int(m["last_confirmed_year"]) if m.get("last_confirmed_year") else None,
            "mandatory_certification": bool(m.get("mandatory_cert")),
            "certification": m.get("certification"),
            "qco_status": m.get("qco_status"),
            "qco_date": m.get("qco_date"),
            "department": m.get("dept_code"),
            "committee": m.get("committee"),
            "ics": m.get("ics"),
        }

    def current_successor(self, kys_id: int) -> dict | None:
        """Follow REPLACED_BY until a current standard, or give up."""
        seen, node = {int(kys_id)}, int(kys_id)
        for _ in range(MAX_REPLACEMENT_HOPS):
            nxt = [r for r in self.kg.get_relationships(node) if r.relationship == REPLACED_BY]
            if not nxt or nxt[0].kys_id in seen:
                return None
            node = nxt[0].kys_id
            seen.add(node)
            if self.meta.get(node, {}).get("status") == "current":
                return self.standard(node)
        return None

    def graph(self, kys_id: int) -> dict:
        """What the knowledge graph adds to one candidate."""
        relations = self.kg.get_relationships(int(kys_id))
        by_type: dict[str, list] = {}
        for rel in relations:
            by_type.setdefault(rel.relationship, []).append(rel)

        normative = []
        for rel in by_type.get(NORMATIVELY_REFERENCES, [])[:MAX_NORMATIVE]:
            info = self.standard(rel.kys_id)
            entry = {"is_number": info["is_number"], "title": info["title"], "status": info["status"],
                     "kys_id": rel.kys_id}
            if info["status"] == "withdrawn":
                successor = self.current_successor(rel.kys_id)
                entry["use_instead"] = (successor["is_number"] if successor
                                        else self.meta.get(rel.kys_id, {}).get("replaced_by_is"))
            normative.append(entry)

        return {
            "normative_references": normative,
            "normative_total": len(by_type.get(NORMATIVELY_REFERENCES, [])),
            "references_total": len(by_type.get(REFERENCES, [])),
            "referenced_by_total": len(by_type.get(REFERENCED_BY, [])),
            "replaces": [{"is_number": r.is_number, "kys_id": r.kys_id}
                         for r in by_type.get(REPLACES, [])][:6],
        }

    def cited(self, citation) -> dict:
        """A standard the tender named: is it still valid, and if not, what replaced it."""
        out = citation.to_dict()
        if citation.kys_id and citation.status == "withdrawn":
            successor = self.current_successor(citation.kys_id)
            if successor:
                out["current_replacement"] = successor
        return out

    # ---------------- document ----------------

    def analyze(self, text: str) -> dict:
        items = self.retriever.search_document(text, top_k=self.top_k)
        out_items = []
        for item in items:
            candidates = []
            for cand in item.candidates:
                entry = cand.to_dict()
                entry["standard"] = self.standard(cand.kys_id)
                entry["graph"] = self.graph(cand.kys_id)
                candidates.append(entry)
            out_items.append({
                "line_item": item.line_item,
                "query_text": item.query_text,
                "requirements": item.requirements.to_dict() if item.requirements else {},
                "cited_standards": [self.cited(c) for c in item.cited_standards],
                "candidates": candidates,
                # Set only when the multilingual layer translated the line:
                # show the English the search actually ran on.
                "line_item_english": getattr(item, "line_item_english", "") or "",
            })
        return {
            "items": out_items,
            "kg_backend": type(self.kg).__name__,
            "dense_retrieval": self.retriever.dense is not None,
        }
