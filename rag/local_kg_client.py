"""
Offline Knowledge Graph client: the same graph as Neo4j, read from the CSVs.

Neo4jKGClient needs a live Aura instance. That is the right home for the
graph, but a demo cannot depend on venue Wi-Fi, so this client answers the
same get_relationships() question from the files Knowlege_Graph/02-07 load
into Neo4j, applying the same rules:

  REFERENCES             every edges.csv row with both ids      (04)
  REPLACED_BY            every standards.csv replaced_by_id      (05)
  NORMATIVELY_REFERENCES every resolved clause 2 reference       (07)

plus the reverse directions the Neo4j query also returns (REFERENCED_BY,
REPLACES). Neighbour titles use the `title` column, as the Neo4j nodes do.
Loads in a few seconds and holds ~200k edges in plain dicts.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd

from rag.kg_client import (
    NORMATIVELY_REFERENCES,
    REFERENCED_BY,
    REFERENCES,
    REPLACED_BY,
    REPLACES,
)
from rag.schemas import RelatedStandard

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "IS_Standards_Data"
NORMATIVE_CSV = REPO_ROOT / "Semantic_Analysis" / "data" / "normative_refs_edges.csv"


class LocalKGClient:
    def __init__(
        self,
        standards_csv: Path = DATA_DIR / "standards.csv",
        edges_csv: Path = DATA_DIR / "edges.csv",
        normative_csv: Path = NORMATIVE_CSV,
    ):
        standards = pd.read_csv(
            standards_csv, usecols=["kys_id", "is_number", "title", "replaced_by_id"], low_memory=False
        )
        self._node = {
            int(k): (str(n), str(t) if isinstance(t, str) else "")
            for k, n, t in zip(standards["kys_id"], standards["is_number"], standards["title"])
        }
        self._edges: dict[int, list[tuple[str, int]]] = defaultdict(list)
        self._seen: set[tuple[int, str, int]] = set()

        edges = pd.read_csv(edges_csv, usecols=["citing_id", "cited_id"]).dropna()
        for citing, cited in zip(edges["citing_id"].astype(int), edges["cited_id"].astype(int)):
            self._add(citing, REFERENCES, cited)
            self._add(cited, REFERENCED_BY, citing)

        replaced = standards.dropna(subset=["replaced_by_id"])
        for old, new in zip(replaced["kys_id"].astype(int), replaced["replaced_by_id"].astype(int)):
            self._add(old, REPLACED_BY, new)
            self._add(new, REPLACES, old)

        if normative_csv.exists():
            normative = pd.read_csv(normative_csv, usecols=["citing_id", "cited_id"]).dropna()
            for citing, cited in zip(normative["citing_id"].astype(int), normative["cited_id"].astype(int)):
                self._add(citing, NORMATIVELY_REFERENCES, cited)

    def _add(self, source: int, relationship: str, target: int) -> None:
        # Neo4j MATCHes both endpoints before MERGE, so an edge to a node that
        # does not exist is never created; mirror that, and MERGE's dedup.
        if source in self._node and target in self._node:
            key = (source, relationship, target)
            if key not in self._seen:
                self._seen.add(key)
                self._edges[source].append((relationship, target))

    def get_relationships(self, kys_id: int) -> list[RelatedStandard]:
        related = []
        for relationship, target in self._edges.get(kys_id, []):
            is_number, title = self._node[target]
            related.append(RelatedStandard(kys_id=target, is_number=is_number, title=title,
                                           relationship=relationship))
        return related

    def close(self) -> None:
        pass
