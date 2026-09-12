"""Checks on the parts that are rules rather than models.

Run with:  python Semantic_Analysis/tests/test_pipeline.py
(No pytest dependency - this is a plain script so it runs anywhere.)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from is_advisor import config, corpus, documents, gazetteer, query, requirements, search  # noqa: E402

FAILURES: list[str] = []


def check(name: str, actual, expected) -> None:
    if actual != expected:
        FAILURES.append(f"{name}\n    expected {expected!r}\n    actual   {actual!r}")


def test_citation_parsing() -> None:
    cases = {
        "IS 1786:2008": ["IS 1786"],
        "is 456 - 2000": ["IS 456"],
        "IS 2911 (Part 1/Sec 4):2010": ["IS 2911 (Part 1)"],
        "IS 8329 Part 1": ["IS 8329 (Part 1)"],
        "conforming to IS/ISO 9001:2015": ["IS 9001"],
        "IS 1786 and IS 432": ["IS 1786", "IS 432"],
        "no standard here": [],
    }
    for text, expected in cases.items():
        check(f"extract_is_numbers({text!r})", query.extract_is_numbers(text), expected)


def test_citations_leave_the_query_text() -> None:
    cleaned = query.strip_boilerplate("TMT bars conforming to IS 1786:2008, quantity 25 MT")
    check("citation removed", "1786" in cleaned, False)
    check("product kept", "TMT" in cleaned, True)


def test_boilerplate_does_not_eat_product_words() -> None:
    """Regression: an unbounded 'no' pattern turned "nominal" into "minal"
    and "NOTICE" into "TICE", silently corrupting the product description."""
    cases = {
        "GI pipes 25mm nominal bore": "nominal",
        "Normal duty cable": "Normal",
        "NOTICE INVITING TENDER": "NOTICE",
        "Nozzle assembly for the sprayer": "Nozzle",
    }
    for text, must_survive in cases.items():
        cleaned = query.strip_boilerplate(text)
        check(f"{must_survive!r} survives {text!r}", must_survive in cleaned, True)

    # ...while the boilerplate itself still goes.
    cleaned = query.strip_boilerplate("Cement bags, quantity 500 nos, rate as per schedule")
    for gone in ("quantity", "schedule", "rate"):
        check(f"{gone!r} stripped", gone in cleaned.lower(), False)
    check("product kept", "Cement" in cleaned, True)


def test_headings_are_dropped() -> None:
    document = (
        "NOTICE INVITING TENDER\n"
        "Schedule of materials:\n"
        "1. TMT reinforcement bars Fe 500D grade\n"
    )
    items = query.parse_document(document)
    check("only the real line item survives", len(items), 1)
    check("it is the product line", "TMT" in items[0].text, True)

    # A heading that cites a standard is still worth keeping.
    kept = query.parse_document("MATERIALS AS PER IS 1786:")
    check("cited heading kept", len(kept), 1)


def test_part_numbers_survive_splitting() -> None:
    row = "Ductile iron pipes DN 300 | IS 8329 (Part 1) | Rs. 45,000"
    items = query.parse_document(row)
    check("single line item", len(items), 1)
    check("part preserved", items[0].cited_is, ["IS 8329 (Part 1)"])


def test_sub_items_split() -> None:
    items = query.parse_document("a) hand pump  b) HDPE tank  c) sluice valve")
    check("three sub-items", len(items), 3)


def test_revision_markers_stripped() -> None:
    check(
        "spaced revision marker",
        corpus.clean_text("Hexagon head bolts Part 1 ( Fifth Revision )"),
        "Hexagon head bolts Part 1",
    )
    check(
        "tight revision marker",
        corpus.clean_text("Ordinary portland cement - Specification (Sixth Revision)"),
        "Ordinary portland cement - Specification",
    )
    check("placeholder aspect", corpus.clean_text("N/A"), "")


def test_index_respects_the_traps() -> None:
    frame = corpus.load_standards()
    index = corpus.build_index_frame(frame)
    check("one row per base id", index["is_base_id"].is_unique, True)
    check("current only", set(index["status"]), {"current"})
    check("canonical only", set(index["is_canonical"]), {True})

    # Trap 1: the latest edition wins even when an older one is still 'current'.
    multi = frame[frame["status"] == "current"].groupby("is_base_id")["is_year"].nunique()
    contested = multi[multi > 1].index[:50]
    for base in contested:
        newest = frame[(frame["is_base_id"] == base) & (frame["status"] == "current")]["is_year"].max()
        picked = index[index["is_base_id"] == base]["is_year"]
        if len(picked) and picked.iloc[0] != newest:
            FAILURES.append(f"stale edition indexed for {base}: {picked.iloc[0]} not {newest}")
            break


def test_specification_block_is_one_line_item() -> None:
    """Option B input: five attributes of one product, not five products."""
    document = (
        "Technical Specification:\n"
        "Product: Water storage tank\n"
        "Capacity: 200 L\n"
        "Material: Stainless steel\n"
        "Installation: Outdoor\n"
        "Warranty: 2 years\n"
    )
    items = query.parse_document(document)
    check("one line item", len(items), 1)
    check("bare heading dropped", "Technical Specification" in items[0].text, False)
    check("all pairs kept", len(items[0].pairs), 5)
    check("commercial value out of the query", "2 years" in items[0].text, False)
    check("material in the query", "Stainless steel" in items[0].text, True)

    # A title line above the block names the product and joins it.
    titled = query.parse_document(
        "Solar water heater, residential\nCapacity: 100 LPD\nMaterial: Evacuated tube\n"
    )
    check("title absorbed", len(titled), 1)
    check("title in query", "Solar water heater" in titled[0].text, True)


def test_a_lone_key_value_line_is_not_a_block() -> None:
    items = query.parse_document("Galvanized MS pipes medium class for plumbing")
    check("plain line unaffected", len(items), 1)
    check("no pairs", items[0].pairs, [])


def test_requirements_worked_example() -> None:
    """The example from the specification, field by field."""
    text = ("Procure 100 stainless steel water storage tanks for outdoor installation, "
            "minimum capacity 500 litres, resistant to corrosion")
    result = requirements.extract(text)
    check("product", result.product, "water storage tank")
    check("material", result.material, ["stainless steel"])
    check("environment", result.environment, ["outdoor"])
    check("property", result.properties, ["corrosion resistant"])
    check("one quantity", len(result.quantities), 1)
    if result.quantities:
        quantity = result.quantities[0]
        check("capacity value", quantity.value, 500.0)
        check("capacity unit", quantity.unit, "L")
        check("capacity field", quantity.field, "capacity")
        check("qualifier", quantity.qualifier, "minimum")
    # The order quantity is not a specification.
    check("count is not a capacity", [q.value for q in result.quantities], [500.0])


def test_quantity_details() -> None:
    ranged = requirements.extract_quantities("8 mm to 32 mm diameter")
    check("range collapses to one", len(ranged), 1)
    if ranged:
        check("range upper bound", ranged[0].value_max, 32.0)

    separate = requirements.extract_quantities("25 mm bore and 40 mm pipe")
    check("unrelated sizes stay separate", len(separate), 2)

    prefix = requirements.extract_quantities("sluice valve DN 150 flanged")
    check("unit-first notation", [(q.unit, q.value) for q in prefix], [("DN", 150.0)])

    indian = requirements.extract_quantities("tank of 1,00,000 L capacity")
    check("Indian digit grouping", [q.value for q in indian], [100000.0])

    # A field word that measures something else must not be borrowed.
    mixed = requirements.extract_quantities("32 mm diameter, quantity 45 MT")
    check("tonnage is a weight", [q.field for q in mixed][-1], "weight")


def test_requirements_from_pairs() -> None:
    result = requirements.from_pairs([
        ("Material", "Stainless steel"), ("Capacity", "200 L"),
        ("Installation", "Outdoor"), ("Colour", "Blue"),
    ])
    check("material from key", result.material, ["Stainless steel"])
    check("environment from key", result.environment, ["Outdoor"])
    check("capacity from key", [(q.value, q.unit) for q in result.quantities], [(200.0, "L")])
    check("unknown key retained", result.unmapped, ["Colour: Blue"])


def test_gazetteers_prefer_the_longer_term() -> None:
    terms = gazetteer.find_terms("stainless steel water tank", "material")
    check("longest match wins", terms, ["stainless steel"])
    check("gazetteer is populated", len(gazetteer.load_gazetteer("material")) > 50, True)


def test_tier_banding() -> None:
    check("top band", search.tier_for(1.0), config.TIER_HIGH)
    check("bottom band", search.tier_for(0.0), config.TIER_POSSIBLE)
    check("bands are ordered", config.TIER_RELATED_MIN < config.TIER_HIGH_MIN, True)


def test_pdf_reading() -> None:
    fixtures = Path(__file__).resolve().parent / "fixtures"
    tender = fixtures / "tender.pdf"
    scanned = fixtures / "scanned.pdf"
    if not tender.exists():
        FAILURES.append("fixtures missing - run tests/make_fixtures.py")
        return

    text = documents.read_document(tender)
    items = query.parse_document(text)
    check("three line items from the PDF", len(items), 3)
    check("citation survives extraction", items[0].cited_is, ["IS 1786"])

    try:
        documents.read_document(scanned)
        FAILURES.append("a scanned PDF was accepted instead of being reported")
    except documents.ScannedPdfError:
        pass


def main() -> int:
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)})")
        for failure in FAILURES:
            print("  " + failure)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
