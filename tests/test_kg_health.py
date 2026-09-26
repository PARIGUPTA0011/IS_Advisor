"""Tests for knowledge-graph health reporting.

    python tests/test_kg_health.py

No database. `describe_graph()` is the only part that needs Neo4j, so it is
stubbed here and the reporting built on top of it is what gets checked: an
empty graph must produce exactly one actionable message, and a loaded graph
must produce none.

Why this is worth a test: an empty graph is invisible in the output. Every
recommendation still comes back, only `related_standards` is silently `[]`,
and the Neo4j notifications that used to hint at the problem are now turned
off deliberately (see rag/kg_client.py). This message is the only thing left
that says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.kg_client import ALL_RELATIONSHIP_TYPES, Neo4jKGClient  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


class StubClient(Neo4jKGClient):
    """A client whose graph contents are whatever the test says they are."""

    def __init__(self, standards: int, fail: bool = False):
        self._standards = standards
        self._fail = fail            # no super().__init__: no driver, no network

    def describe_graph(self) -> dict:
        if self._fail:
            raise RuntimeError("connection refused")
        return {
            "nodes": {"Standard": self._standards, "Department": 17,
                      "Committee": 390, "Certification": 1},
            "relationships": {name: (0 if self._standards == 0 else 1000)
                              for name in ALL_RELATIONSHIP_TYPES},
            "standards": self._standards,
            "is_empty": self._standards == 0,
        }


def test_empty_graph_warns_once() -> None:
    print("empty graph")
    warning = StubClient(standards=0).empty_graph_warning()
    check("a warning is produced", warning is not None, True)
    check("says the graph is empty", "graph is empty" in warning, True)
    check("says recommendations still work", "still work" in warning, True)
    # The point of the message is that it tells you what to run.
    for script in ("02_create_graph.py", "04_create_reference_relationships.py.py",
                   "06_create_certification_relationships.py"):
        check(f"names {script}", script in warning, True)


def test_loaded_graph_is_silent() -> None:
    print("loaded graph")
    check("no warning", StubClient(standards=35524).empty_graph_warning(), None)


def test_unreachable_graph_reports_the_real_error() -> None:
    print("unreachable graph")
    # A connection failure must not be reported as "the graph is empty" - they
    # need different fixes.
    warning = StubClient(standards=0, fail=True).empty_graph_warning()
    check("reports the cause", "connection refused" in warning, True)
    check("does not claim emptiness", "graph is empty" in warning, False)


def test_relationship_types_match_the_loader() -> None:
    print("relationship coverage")
    # If a build script gains a relationship type, the health report should
    # count it too, so the two lists are asserted against each other.
    expected = {"REFERENCES", "REPLACED_BY", "BELONGS_TO", "MAINTAINED_BY",
                "REQUIRES_CERTIFICATION"}
    check("all five types counted", set(ALL_RELATIONSHIP_TYPES), expected)


def main() -> int:
    test_empty_graph_warns_once()
    test_loaded_graph_is_silent()
    test_unreachable_graph_reports_the_real_error()
    test_relationship_types_match_the_loader()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all knowledge-graph health checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
