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


def load_eval_set(path=config.EVAL_SET) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def evaluate(retriever, items: list[dict], *, use_reranker: bool, use_bm25: bool,
             use_dense: bool) -> dict:
    """Recall@k and MRR over the eval set for one retriever configuration."""
    base_by_kys = dict(zip(retriever.corpus["kys_id"], retriever.corpus["is_base_id"]))
    hits = {k: 0 for k in K_VALUES}
    reciprocal_total = 0.0
    misses: list[tuple[str, list[str]]] = []

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
        )
        gold = set(item["gold"])
        ranks = [i for i, c in enumerate(ranked, 1) if base_by_kys.get(c.kys_id) in gold]
        best = min(ranks) if ranks else None
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
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate IS-Advisor retrieval.")
    parser.add_argument("--ablate", action="store_true", help="run every configuration")
    parser.add_argument("--show-misses", type=int, default=0, help="print N items missed at rank 5")
    args = parser.parse_args()

    items = load_eval_set()
    print(f"Evaluation set: {len(items)} line items\n")

    # The evaluation always loads the cross-encoder, even though it is off by
    # default at query time, because measuring it is the whole point here.
    retriever = load_retriever(with_spacy=False, with_reranker=True)
    has_dense = retriever.dense is not None
    has_rerank = retriever.cross_encoder is not None
    if not has_dense:
        print("! dense index unavailable - keyword-only results below")
    if not has_rerank:
        print("! cross-encoder unavailable - reranked rows skipped")

    configs = [("hybrid (shipping default)", False, True, True)]
    if args.ablate:
        configs = [
            ("BM25 only", False, True, False),
            ("dense only", False, False, True),
            ("hybrid (RRF)", False, True, True),
            ("BM25 + reranker", True, True, False),
            ("dense + reranker", True, False, True),
            ("hybrid + reranker", True, True, True),
        ]

    rows, last_misses = [], []
    for name, rerank_on, bm25_on, dense_on in configs:
        if dense_on and not has_dense:
            continue
        if rerank_on and not has_rerank:
            continue
        start = time.time()
        scores = evaluate(retriever, items, use_reranker=rerank_on, use_bm25=bm25_on,
                          use_dense=dense_on)
        last_misses = scores.pop("_misses")
        scores["config"] = name
        scores["sec/query"] = (time.time() - start) / len(items)
        rows.append(scores)
        print(f"  {name:22s} R@5={scores['recall@5']:.3f}  R@10={scores['recall@10']:.3f}")

    table = pd.DataFrame(rows)[["config", "recall@1", "recall@5", "recall@10", "mrr", "sec/query"]]
    print("\n" + table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    if args.show_misses:
        print(f"\nMissed at rank 5 ({len(last_misses)} of {len(items)}):")
        for text, gold in last_misses[: args.show_misses]:
            print(f"  {', '.join(gold):26s} <- {text[:70]}")

    out = config.ARTIFACTS / "eval_results.csv"
    table.to_csv(out, index=False)
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
