"""Fit the relevance-tier thresholds to the evaluation set.

A threshold on a fused score means nothing until it is measured against known
answers, so this picks the two cut points from where gold standards actually
score rather than from round numbers, and reports what the choice costs.

    python Semantic_Analysis/06_calibrate_tiers.py
    python Semantic_Analysis/06_calibrate_tiers.py --apply     # write to config.py

Thresholds fitted here inherit every caveat of the evaluation set: the items are
hand-written, so the score distribution is optimistic. See README section 8.
"""
from __future__ import annotations

import argparse
import re
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from is_advisor import config  # noqa: E402
from is_advisor.query import strip_boilerplate  # noqa: E402
from is_advisor.search import load_retriever  # noqa: E402

load_eval_set = import_module("02_evaluate").load_eval_set

# Aim for a top tier that holds most correct answers without swallowing the list.
TARGET_GOLD_IN_TOP = 0.70
TARGET_RELATED_RECALL = 0.95


def collect(retriever, items: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """Scores of gold candidates and of everything else, over the eval set."""
    base_by_kys = dict(zip(retriever.corpus["kys_id"], retriever.corpus["is_base_id"]))
    gold_scores: list[float] = []
    other_scores: list[float] = []

    for item in items:
        query = strip_boilerplate(item["text"]) or item["text"]
        ranked = retriever.retrieve(query, top_k=10)
        wanted = set(item["gold"])
        for candidate in ranked:
            target = gold_scores if base_by_kys.get(candidate.kys_id) in wanted else other_scores
            target.append(candidate.score)
    return np.array(gold_scores), np.array(other_scores)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate relevance tier thresholds.")
    parser.add_argument("--apply", action="store_true", help="write the fitted values into config.py")
    args = parser.parse_args()

    items = load_eval_set()
    retriever = load_retriever(with_spacy=False)
    gold, other = collect(retriever, items)
    if gold.size == 0:
        print("No gold candidates retrieved - cannot calibrate.")
        return 1

    print(f"Evaluation set: {len(items)} items")
    print(f"  gold candidates retrieved in top 10: {gold.size}")
    print(f"  other candidates:                    {other.size}\n")
    print("  gold score distribution")
    for label, value in [("min", gold.min()), ("25th", np.percentile(gold, 25)),
                         ("median", np.median(gold)), ("75th", np.percentile(gold, 75)),
                         ("max", gold.max())]:
        print(f"    {label:7s} {value:.3f}")

    # The top tier should hold most gold answers; the middle tier should hold
    # nearly all of the rest.
    high = float(np.percentile(gold, (1 - TARGET_GOLD_IN_TOP) * 100))
    related = float(np.percentile(gold, (1 - TARGET_RELATED_RECALL) * 100))
    high, related = round(high, 2), round(related, 2)
    if related >= high:
        related = round(high - 0.05, 2)

    print(f"\n  fitted thresholds: high >= {high:.2f}, related >= {related:.2f}")
    in_high = float((gold >= high).mean())
    in_related = float(((gold >= related) & (gold < high)).mean())
    in_possible = float((gold < related).mean())
    print(f"  share of gold answers landing in each tier:")
    print(f"    {config.TIER_HIGH:18s} {in_high:.1%}")
    print(f"    {config.TIER_RELATED:18s} {in_related:.1%}")
    print(f"    {config.TIER_POSSIBLE:18s} {in_possible:.1%}")
    if other.size:
        print(f"  non-gold candidates reaching the top tier: {float((other >= high).mean()):.1%}")
        print("  (many are genuinely relevant standards the eval set does not name,")
        print("   so this is an upper bound on the false-positive rate, not a measure of it)")

    if args.apply:
        path = Path(config.__file__)
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^TIER_HIGH_MIN = .*$", f"TIER_HIGH_MIN = {high:.2f}", text, flags=re.M)
        text = re.sub(r"^TIER_RELATED_MIN = .*$", f"TIER_RELATED_MIN = {related:.2f}", text, flags=re.M)
        path.write_text(text, encoding="utf-8")
        print(f"\nWrote thresholds into {path.name}")
    else:
        print("\nRe-run with --apply to write these into config.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
