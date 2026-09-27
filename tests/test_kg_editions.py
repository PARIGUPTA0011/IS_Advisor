"""Tests for one-edition-per-standard pruning of related standards.

    python tests/test_kg_editions.py

No database and no metadata file: the store is stubbed, so these assert the
rule itself. The rule has to match
`Semantic_Analysis/is_advisor/corpus.py::select_index_rows` - current and
canonical, then highest is_year, tie-broken on the higher kys_id - because the
two halves of the system otherwise disagree about what "the current edition"
means.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.kg_editions import annotate, prune_superseded_editions  # noqa: E402
from rag.schemas import RelatedStandard, StandardRecord  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


class StubStore:
    """Just the two lookups kg_editions uses."""

    def __init__(self, records: list[StandardRecord]):
        self._by_id = {r.kys_id: r for r in records}

    def get(self, kys_id: int):
        return self._by_id.get(kys_id)


def record(kys_id: int, is_number: str, base: str, year: int | None, status: str,
           title: str = "") -> StandardRecord:
    return StandardRecord(
        kys_id=kys_id, is_number=is_number, title=title or f"Title for {is_number}",
        status=status, is_base_id=base, is_year=year, is_canonical=True,
    )


def relation(kys_id: int, is_number: str, relationship: str = "REFERENCES") -> RelatedStandard:
    return RelatedStandard(kys_id=kys_id, is_number=is_number, title="", relationship=relationship)


# The case from the live run: one base standard, two editions, both real edges.
TWO_EDITIONS = StubStore([
    record(1, "IS 10322 (Part 5/Sec 3):2012", "IS 10322 (Part 5/Sec 3)", 2012, "withdrawn"),
    record(2, "IS 10322 (Part 5/Sec 3):2026", "IS 10322 (Part 5/Sec 3)", 2026, "current"),
])


def test_keeps_only_the_current_edition() -> None:
    print("two editions of one standard")
    relations = [relation(1, "IS 10322 (Part 5/Sec 3):2012"),
                 relation(2, "IS 10322 (Part 5/Sec 3):2026")]
    pruned = prune_superseded_editions(relations, TWO_EDITIONS)
    check("one survives", len(pruned), 1)
    check("the current one", pruned[0].is_number, "IS 10322 (Part 5/Sec 3):2026")
    check("status attached", pruned[0].status, "current")
    check("title filled from the store", pruned[0].title, "Title for IS 10322 (Part 5/Sec 3):2026")


def test_order_of_arrival_does_not_matter() -> None:
    print("same two editions, reversed")
    relations = [relation(2, "IS 10322 (Part 5/Sec 3):2026"),
                 relation(1, "IS 10322 (Part 5/Sec 3):2012")]
    pruned = prune_superseded_editions(relations, TWO_EDITIONS)
    check("still one", len(pruned), 1)
    check("still the current one", pruned[0].is_number, "IS 10322 (Part 5/Sec 3):2026")


def test_current_beats_a_newer_withdrawn_edition() -> None:
    print("newer edition is withdrawn")
    # Status dominates the year: a withdrawn 2030 edition must not displace a
    # current 2020 one, which is what sorting on year alone would do.
    store = StubStore([
        record(1, "IS 999:2020", "IS 999", 2020, "current"),
        record(2, "IS 999:2030", "IS 999", 2030, "withdrawn"),
    ])
    pruned = prune_superseded_editions(
        [relation(1, "IS 999:2020"), relation(2, "IS 999:2030")], store)
    check("current wins", pruned[0].is_number, "IS 999:2020")


def test_all_withdrawn_keeps_the_newest_and_marks_it() -> None:
    print("every edition withdrawn")
    # Dropping the group entirely would hide a real edge. "The standard it
    # references was withdrawn" is a fact worth surfacing, so it is kept - and
    # marked, so it cannot read like a live recommendation.
    store = StubStore([
        record(1, "IS 888:1990", "IS 888", 1990, "withdrawn"),
        record(2, "IS 888:2001", "IS 888", 2001, "withdrawn"),
    ])
    pruned = prune_superseded_editions(
        [relation(1, "IS 888:1990"), relation(2, "IS 888:2001")], store)
    check("kept, not dropped", len(pruned), 1)
    check("the newest of them", pruned[0].is_number, "IS 888:2001")
    check("marked withdrawn", pruned[0].status, "withdrawn")


def test_different_standards_are_both_kept() -> None:
    print("different standards")
    store = StubStore([
        record(1, "IS 1786:2008", "IS 1786", 2008, "current"),
        record(2, "IS 432 (Part 1):2026", "IS 432 (Part 1)", 2026, "current"),
    ])
    pruned = prune_superseded_editions(
        [relation(1, "IS 1786:2008"), relation(2, "IS 432 (Part 1):2026")], store)
    check("both survive", len(pruned), 2)
    check("input order preserved", [p.kys_id for p in pruned], [1, 2])


def test_parts_are_separate_standards() -> None:
    print("parts of one family")
    # IS 2062 (Part 1) and (Part 2) are different base ids, so both stay. This
    # is the case that a naive "strip the year and dedupe" would get wrong.
    store = StubStore([
        record(1, "IS 2062 (Part 1):2025", "IS 2062 (Part 1)", 2025, "current"),
        record(2, "IS 2062 (Part 2):2026", "IS 2062 (Part 2)", 2026, "current"),
    ])
    pruned = prune_superseded_editions(
        [relation(1, "IS 2062 (Part 1):2025"), relation(2, "IS 2062 (Part 2):2026")], store)
    check("both parts kept", len(pruned), 2)


def test_same_standard_under_two_relationship_types() -> None:
    print("same standard, two relationship types")
    # Grouping is per (relationship, base id): a standard that is both
    # referenced and a replacement must appear under both, or one of the two
    # relationships silently disappears.
    relations = [relation(2, "IS 10322 (Part 5/Sec 3):2026", "REFERENCES"),
                 relation(2, "IS 10322 (Part 5/Sec 3):2026", "REPLACED_BY")]
    pruned = prune_superseded_editions(relations, TWO_EDITIONS)
    check("both relationships kept", sorted(p.relationship for p in pruned),
          ["REFERENCES", "REPLACED_BY"])


def test_unknown_standard_is_kept_untouched() -> None:
    print("standard missing from the store")
    # A graph node with no dataset row has no base id to group on. Keeping it is
    # the safe direction: it is a real edge, and the alternative is dropping
    # evidence because a lookup failed.
    pruned = prune_superseded_editions([relation(999, "IS 7777:1999")], StubStore([]))
    check("kept", len(pruned), 1)
    check("no status invented", pruned[0].status, None)


def test_undated_edition_loses_to_a_dated_one() -> None:
    print("edition with no year")
    store = StubStore([
        record(1, "IS 555", "IS 555", None, "current"),
        record(2, "IS 555:2015", "IS 555", 2015, "current"),
    ])
    pruned = prune_superseded_editions(
        [relation(1, "IS 555"), relation(2, "IS 555:2015")], store)
    check("dated edition wins", pruned[0].is_number, "IS 555:2015")


def test_annotate_leaves_relations_alone_when_unknown() -> None:
    print("annotate only")
    annotated = annotate([relation(1, "IS 10322 (Part 5/Sec 3):2012")], TWO_EDITIONS)
    check("status filled", annotated[0].status, "withdrawn")
    check("base id filled", annotated[0].is_base_id, "IS 10322 (Part 5/Sec 3)")
    check("year filled", annotated[0].is_year, 2012)
    check("nothing pruned", len(annotated), 1)


def main() -> int:
    test_keeps_only_the_current_edition()
    test_order_of_arrival_does_not_matter()
    test_current_beats_a_newer_withdrawn_edition()
    test_all_withdrawn_keeps_the_newest_and_marks_it()
    test_different_standards_are_both_kept()
    test_parts_are_separate_standards()
    test_same_standard_under_two_relationship_types()
    test_unknown_standard_is_kept_untouched()
    test_undated_edition_loses_to_a_dated_one()
    test_annotate_leaves_relations_alone_when_unknown()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all edition-pruning checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
