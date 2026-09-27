"""Tests for the deterministic specification-coverage check.

    python tests/test_spec_coverage.py

No model, no database. The point of this module is that the same query and the
same evidence always produce the same caveat - one run of the pipeline warned
that IP66 was not covered and the next, on the identical query, did not, because
the warning depended on the model choosing to mention it. These tests pin the
behaviour that replaced it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.schemas import Evidence, RelatedStandard, StandardRecord  # noqa: E402
from rag.spec_coverage import (  # noqa: E402
    check_coverage,
    coverage_warning,
    extract_spec_terms,
    unsupported_terms,
)

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


def evidence(is_number: str, title: str, **fields) -> Evidence:
    return Evidence(
        kys_id=abs(hash(is_number)) % 100000,
        score=0.9,
        matched_text=None,
        record=StandardRecord(kys_id=1, is_number=is_number, title=title, **fields),
    )


LED = evidence(
    "IS 16107 (Part 2/Sec 2):2017",
    "Luminaries Performance Part 2 Particular Requirements Section 2 LED Street Lighting",
    aspect="Product Specification",
)


def test_extracts_the_values_a_query_asks_for() -> None:
    print("extraction")
    terms = [t.text for t in extract_spec_terms("90W LED street light IP66 at 230V AC")]
    check("wattage found", "90W" in terms, True)
    check("ip rating found", "IP66" in terms, True)
    check("voltage found", "230V" in terms, True)
    # "LED" has no digits, so it is a word, not a specification value.
    check("plain words are not spec terms", "LED" in terms, False)


def test_citations_are_not_spec_terms() -> None:
    print("citations excluded")
    terms = [t.text for t in extract_spec_terms("TMT bars conforming to IS 1786:2008, Fe500D")]
    check("IS number excluded", any("1786" in t for t in terms), False)
    check("grade code included", "Fe500D" in terms, True)


def test_bare_numbers_are_not_spec_terms() -> None:
    print("bare numbers excluded")
    # "100" on its own claims nothing - it is a quantity ordered, not a
    # specification the standard could confirm.
    check("bare count ignored", extract_spec_terms("Procure 100 water tanks"), [])


def test_uncovered_values_are_reported() -> None:
    print("values the evidence does not state")
    missing = unsupported_terms("90W LED street light IP66", [LED])
    check("both reported", sorted(missing), ["90W", "IP66"])
    warning = coverage_warning("90W LED street light IP66", [LED])
    check("warning produced", warning is not None, True)
    check("names the values", "IP66" in warning and "90W" in warning, True)
    check("explains why", "no clause text" in warning, True)
    # Wording matters: not evidenced is not the same as not compliant.
    check("does not claim non-compliance", "compliant" in warning.lower(), False)


def test_covered_values_are_not_reported() -> None:
    print("values the evidence does state")
    covered = evidence("IS 9999:2020", "Luminaire for street lighting rated IP66 at 90W")
    check("nothing missing", unsupported_terms("90W street light IP66", [covered]), [])
    check("no warning", coverage_warning("90W street light IP66", [covered]), None)


def test_spacing_and_case_do_not_matter() -> None:
    print("IP 66 covers IP66")
    spaced = evidence("IS 9999:2020", "Street lighting luminaire, ip 66 protection, 90 w")
    check("separator-insensitive", unsupported_terms("IP66 90W", [spaced]), [])


def test_coverage_names_the_standard_that_states_it() -> None:
    print("which standard covers it")
    covered = evidence("IS 9999:2020", "Luminaire rated IP66")
    terms = {t.text: t.covered_by for t in check_coverage("IP66 90W", [covered, LED])}
    check("attributed to the right standard", terms["IP66"], "IS 9999:2020")
    check("uncovered stays None", terms["90W"], None)


def test_a_related_standard_title_counts_as_evidence() -> None:
    print("KG neighbour titles count")
    # A value named by a related standard's title is still named by the
    # evidence that was put in front of the model.
    with_neighbour = Evidence(
        kys_id=1, score=0.9, matched_text=None,
        record=StandardRecord(kys_id=1, is_number="IS 1:2020", title="Street lighting luminaire"),
        kg_relations=[RelatedStandard(kys_id=2, is_number="IS 2:2020",
                                      title="Degrees of protection IP66 enclosures",
                                      relationship="REFERENCES")],
    )
    check("covered via the neighbour", unsupported_terms("IP66", [with_neighbour]), [])


def test_no_evidence_produces_no_spec_warning() -> None:
    print("no evidence at all")
    # The no-evidence case already has its own warning; adding this one on top
    # would be noise about a query that returned nothing.
    check("silent", coverage_warning("90W IP66", []), None)


def test_the_answer_is_the_same_every_time() -> None:
    print("determinism")
    query = "90W LED street light IP66 230V"
    runs = {tuple(unsupported_terms(query, [LED])) for _ in range(20)}
    check("one distinct result over 20 runs", len(runs), 1)


def test_long_lists_are_summarised() -> None:
    print("many values")
    query = "IP66 90W 230V 25mm 500L Fe500D K9 M25 PN16 DN150"
    warning = coverage_warning(query, [LED])
    check("summarised rather than endless", "more" in warning, True)


def main() -> int:
    test_extracts_the_values_a_query_asks_for()
    test_citations_are_not_spec_terms()
    test_bare_numbers_are_not_spec_terms()
    test_uncovered_values_are_reported()
    test_covered_values_are_not_reported()
    test_spacing_and_case_do_not_matter()
    test_coverage_names_the_standard_that_states_it()
    test_a_related_standard_title_counts_as_evidence()
    test_no_evidence_produces_no_spec_warning()
    test_the_answer_is_the_same_every_time()
    test_long_lists_are_summarised()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all spec-coverage checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
