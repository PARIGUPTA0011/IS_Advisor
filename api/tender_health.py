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