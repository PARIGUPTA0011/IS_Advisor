"""One edition per standard in the related-standards list.

The graph holds every edition of every standard, because it is built from the
whole dataset - so a single `REFERENCES` edge set can legitimately contain
`IS 10322 (Part 5/Sec 3):2012` *and* `IS 10322 (Part 5/Sec 3):2026`. Both are
real edges. Showing both to a procurement officer is still wrong: they are the
same standard, one superseded by the other, and the older one must never be
quoted in a tender.

The rule here is deliberately the same one the retrieval index uses
(`Semantic_Analysis/is_advisor/corpus.py::select_index_rows`), so the two halves
of the system agree on what "the current edition" means:

    status == "current" AND is_canonical, then the highest is_year,
    tie-broken on the higher kys_id

Two deliberate differences from the index, both because this is an evidence
list rather than a search index:

* **A group with no current edition keeps its newest withdrawn edition** rather
  than disappearing. The index is a list of things to recommend, so a withdrawn
  standard has no business in it. This is a list of things a standard is
  *connected to*, and "the standard it references was withdrawn" is exactly the
  kind of fact the graph exists to surface. It is kept and marked.
* **Status travels with the result.** Every surviving relation carries its
  `status`, so a withdrawn one can be labelled as such wherever it is shown
  instead of looking like a live recommendation.
"""

from __future__ import annotations

import dataclasses

from rag.metadata_store import MetadataStore
from rag.schemas import RelatedStandard

CURRENT = "current"


def _sort_key(relation: RelatedStandard) -> tuple[int, int, int]:
    """Higher is better: current first, then newest year, then higher kys_id.

    A missing year sorts below every known year (the index uses -1 for the same
    reason), so a dated edition always beats an undated one.
    """
    is_current = 1 if (relation.status or "").lower() == CURRENT else 0
    year = relation.is_year if relation.is_year is not None else -1
    return (is_current, year, relation.kys_id)


def annotate(relations: list[RelatedStandard], store: MetadataStore) -> list[RelatedStandard]:
    """Fill status / is_base_id / is_year on each relation from the metadata store.

    The graph nodes carry `status` but not `is_base_id` or `is_year`
    (`Knowlege_Graph/02_create_graph.py` does not set them), and the dataset
    does - so these come from the store rather than being re-derived by parsing
    the IS number, which would be a second, disagreeing implementation of what
    an edition is.
    """
    annotated: list[RelatedStandard] = []
    for relation in relations:
        record = store.get(relation.kys_id)
        if record is None:
            annotated.append(relation)
            continue
        annotated.append(
            dataclasses.replace(
                relation,
                status=record.status,
                is_base_id=record.is_base_id,
                is_year=record.is_year,
                title=relation.title or record.title,
            )
        )
    return annotated


def prune_superseded_editions(
    relations: list[RelatedStandard], store: MetadataStore
) -> list[RelatedStandard]:
    """Keep one edition per (relationship, base standard), the current latest.

    Input order is preserved: the first time a group is seen fixes where its
    winner appears, so a caller's ranking is not silently reshuffled.
    """
    annotated = annotate(relations, store)

    best: dict[tuple[str, str], RelatedStandard] = {}
    order: list[tuple[str, str]] = []
    ungrouped: list[RelatedStandard] = []

    for relation in annotated:
        if not relation.is_base_id:
            # No base id means nothing to group on - keep it as it came in
            # rather than guessing, which is how a standard with an unparsable
            # number would otherwise get dropped.
            ungrouped.append(relation)
            continue
        key = (relation.relationship, relation.is_base_id)
        if key not in best:
            best[key] = relation
            order.append(key)
        elif _sort_key(relation) > _sort_key(best[key]):
            best[key] = relation

    pruned = [best[key] for key in order]
    return pruned + ungrouped


def superseded_count(
    relations: list[RelatedStandard], pruned: list[RelatedStandard]
) -> int:
    """How many relations the pruning removed, for reporting."""
    return max(len(relations) - len(pruned), 0)
