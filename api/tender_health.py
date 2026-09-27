from dataclasses import dataclass, field

from Semantic_Analysis.is_advisor.search import CitedStandard, ItemResult


@dataclass
class TenderHealthReport:
    total_items: int
    items_with_citations: int
    items_without_citations: int
    unique_standards_cited: int
    current_standards: int
    outdated_standards: int
    standards: list[CitedStandard] = field(default_factory=list)
    items_without_standards: list[str] = field(default_factory=list)


def build_health_report(results: list[ItemResult]) -> TenderHealthReport:
    items_without_standards: list[str] = []
    all_standards: list[CitedStandard] = []

    for item in results:
        if not item.cited_standards:
            items_without_standards.append(item.line_item)

        all_standards.extend(item.cited_standards)

    unique_standards: dict[str, CitedStandard] = {}

    for standard in all_standards:
        key = standard.is_number or standard.cited_as
        unique_standards[key] = standard

    current_standards = sum(
        1
        for standard in unique_standards.values()
        if standard.status == "current"
    )

    outdated_standards = sum(
        1
        for standard in unique_standards.values()
        if standard.status != "current"
    )

    return TenderHealthReport(
        total_items=len(results),
        items_with_citations=len(results) - len(items_without_standards),
        items_without_citations=len(items_without_standards),
        unique_standards_cited=len(unique_standards),
        current_standards=current_standards,
        outdated_standards=outdated_standards,
        standards=list(unique_standards.values()),
        items_without_standards=items_without_standards,
    )