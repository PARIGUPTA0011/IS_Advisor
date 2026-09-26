"""Measure Recall@5 / Recall@10 on the evaluation set, with ablations.

    python Semantic_Analysis/02_evaluate.py             # the full pipeline
    python Semantic_Analysis/02_evaluate.py --ablate    # every configuration

The point of the ablation table is to show whether the reranker, the dense
retriever and the mined vocabulary each earn their cost, instead of assuming it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from is_advisor import config  # noqa: E402
from is_advisor.query import strip_boilerplate  # noqa: E402
from is_advisor.search import load_retriever  # noqa: E402

K_VALUES = (1, 5, 10)

# The families data/SCOPE_TEXT.md section 1 names as the documented misses:
# the query names a family and the index holds near-identical part titles.
# Scope text exists to fix these, so they are reported on their own.
MISS_FAMILIES = ("IS 1367", "IS 2556", "IS 10124", "IS 13730", "IS 1554", "IS 2062",
                 "IS 7098", "IS 458", "IS 8329")


def in_miss_family(item: dict) -> bool:
    return any(g == f or g.startswith(f + " (") for g in item["gold"] for f in MISS_FAMILIES)


EVAL_SETS = {"hand": config.EVAL_SET, "tenders": config.EVAL_TENDERS}


def load_eval_set(path=config.EVAL_SET) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evaluate(retriever, items: list[dict], *, use_reranker: bool, use_bm25: bool,
             use_dense: bool, use_scope: bool = config.USE_SCOPE_RETRIEVER) -> dict:
    """Recall@k and MRR over the eval set for one retriever configuration."""
    base_by_kys = dict(zip(retriever.corpus["kys_id"], retriever.corpus["is_base_id"]))
    hits = {k: 0 for k in K_VALUES}
    reciprocal_total = 0.0
    misses: list[tuple[str, list[str]]] = []
    best_ranks: list[int | None] = []

    for item in items:
        # Queries go through the same cleaning the live pipeline applies, and
        # citations are stripped, so this measures description -> standard only.
        query = strip_boilerplate(item["text"]) or item["text"]
        ranked = retriever.retrieve(
            query,
            top_k=max(K_VALUES),
            use_reranker=use_reranker,
            use_bm25=use_bm25,
            use_dense=use_dense,
            use_scope=use_scope,
        )
        gold = set(item["gold"])
        ranks = [i for i, c in enumerate(ranked, 1) if base_by_kys.get(c.kys_id) in gold]
        best = min(ranks) if ranks else None
        best_ranks.append(best)
        for k in K_VALUES:
            if best is not None and best <= k:
                hits[k] += 1
        reciprocal_total += 1.0 / best if best else 0.0
        if best is None or best > 5:
            misses.append((item["text"], item["gold"]))

    total = len(items)
    result = {f"recall@{k}": hits[k] / total for k in K_VALUES}
    result["mrr"] = reciprocal_total / total
    result["_misses"] = misses
    result["_ranks"] = best_ranks
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate IS-Advisor retrieval.")
    parser.add_argument("--ablate", action="store_true", help="run every configuration")
    parser.add_argument("--show-misses", type=int, default=0, help="print N items missed at rank 5")
    parser.add_argument("--families", action="store_true",
                        help="also report the SCOPE_TEXT.md miss families item by item")
    parser.add_argument("--set", choices=sorted(EVAL_SETS), default="hand",
                        help="hand = hand-written items; tenders = real tender BOQ lines")
    args = parser.parse_args()

    items = load_eval_set(EVAL_SETS[args.set])
    print(f"Evaluation set '{args.set}': {len(items)} line items\n")

    # The evaluation always loads the cross-encoder, even though it is off by
    # default at query time, because measuring it is the whole point here.
    retriever = load_retriever(with_spacy=False, with_reranker=True)
    has_dense = retriever.dense is not None
    has_rerank = retriever.cross_encoder is not None
    has_scope = retriever.scope_bm25 is not None
    if not has_dense:
        print("! dense index unavailable - keyword-only results below")
    if not has_rerank:
        print("! cross-encoder unavailable - reranked rows skipped")
    if not has_scope:
        print("! scope index unavailable - scope rows run without it")

    # (name, reranker, keyword BM25, dense, scope BM25)
    configs = [("hybrid (shipping default)", False, True, True, config.USE_SCOPE_RETRIEVER)]
    if args.ablate:
        # "no scope retriever" rows still embed scope text on the dense side;
        # comparing against an index built without it needs --no-scope.
        configs = [
            ("BM25 only", False, True, False, False),
            ("scope BM25 only", False, False, False, True),
            ("dense only", False, False, True, False),
            ("hybrid, no scope retriever", False, True, True, False),
            ("hybrid + scope (RRF)", False, True, True, True),
            ("BM25 + reranker", True, True, False, False),
            ("dense + reranker", True, False, True, False),
            ("hybrid + scope + reranker", True, True, True, True),
        ]

    rows, last_misses, family_ranks = [], [], {}
    for name, rerank_on, bm25_on, dense_on, scope_on in configs:
        if dense_on and not has_dense:
            continue
        if rerank_on and not has_rerank:
            continue
        if scope_on and not has_scope and not (bm25_on or dense_on):
            continue
        start = time.time()
        scores = evaluate(retriever, items, use_reranker=rerank_on, use_bm25=bm25_on,
                          use_dense=dense_on, use_scope=scope_on)
        last_misses = scores.pop("_misses")
        ranks = scores.pop("_ranks")
        family = [(item, r) for item, r in zip(items, ranks) if in_miss_family(item)]
        scores["family_recall@5"] = (
            sum(r is not None and r <= 5 for _, r in family) / len(family) if family else float("nan")
        )
        family_ranks[name] = family
        scores["config"] = name
        scores["sec/query"] = (time.time() - start) / len(items)
        rows.append(scores)
        print(f"  {name:28s} R@5={scores['recall@5']:.3f}  R@10={scores['recall@10']:.3f}"
              f"  family R@5={scores['family_recall@5']:.3f}")

    table = pd.DataFrame(rows)[["config", "recall@1", "recall@5", "recall@10", "mrr",
                                "family_recall@5", "sec/query"]]
    print("\n" + table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    if args.families and family_ranks:
        names = list(family_ranks)
        print("\nMiss families, rank of the first gold standard (- = not in top 10):")
        print("  " + "  ".join(f"{n[:14]:>14s}" for n in names) + "  item")
        for i, (item, _) in enumerate(family_ranks[names[0]]):
            cells = "  ".join(f"{'-' if r is None else r:>14}" for r in
                              (family_ranks[n][i][1] for n in names))
            print(f"  {cells}  {', '.join(item['gold'])} <- {item['text'][:55]}")

    if args.show_misses:
        print(f"\nMissed at rank 5 ({len(last_misses)} of {len(items)}):")
        for text, gold in last_misses[: args.show_misses]:
            print(f"  {', '.join(gold):26s} <- {text[:70]}")

    out = config.ARTIFACTS / ("eval_results.csv" if args.set == "hand" else f"eval_results_{args.set}.csv")
    table.to_csv(out, index=False)
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
