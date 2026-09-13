"""Does the mined vocabulary actually earn its place?

Rebuilds the corpus with each vocabulary source switched off and re-measures.
This is the question the plan asks - whether past-edition wording and the
curated trade names pay for themselves - answered with numbers instead of
assumption. Keyword-only retrieval is used throughout, because that is the
only retriever that reads the enriched text.

    python Semantic_Analysis/04_ablate_vocabulary.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from is_advisor import config, corpus as corpus_mod  # noqa: E402
from is_advisor.lexical import BM25Index  # noqa: E402
from is_advisor.query import strip_boilerplate  # noqa: E402
from is_advisor.search import Retriever  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

load_eval_set = import_module("02_evaluate").load_eval_set


def score(frame: pd.DataFrame, items: list[dict]) -> dict:
    retriever = Retriever(frame, BM25Index(frame["lexical_text"].tolist(), frame["kys_id"].tolist()))
    base_by_kys = dict(zip(frame["kys_id"], frame["is_base_id"]))
    hits = {1: 0, 5: 0, 10: 0}
    for item in items:
        query = strip_boilerplate(item["text"]) or item["text"]
        ranked = retriever.retrieve(query, top_k=10, use_reranker=False, use_dense=False)
        gold = set(item["gold"])
        ranks = [i for i, c in enumerate(ranked, 1) if base_by_kys.get(c.kys_id) in gold]
        best = min(ranks) if ranks else None
        for k in hits:
            if best and best <= k:
                hits[k] += 1
    return {f"recall@{k}": hits[k] / len(items) for k in hits}


def main() -> int:
    items = load_eval_set()
    print(f"Evaluation set: {len(items)} line items (keyword retrieval only)\n")

    settings = [
        ("title + classification only", False, False),
        ("+ past-edition vocabulary", True, False),
        ("+ curated trade names", False, True),
        ("both (shipping default)", True, True),
    ]
    rows = []
    for name, past, aliases in settings:
        frame = corpus_mod.build_corpus(use_past_editions=past, use_aliases=aliases)
        result = {"corpus": name, **score(frame, items)}
        rows.append(result)
        print(f"  {name:30s} R@5={result['recall@5']:.3f}  R@10={result['recall@10']:.3f}")

    table = pd.DataFrame(rows)
    print("\n" + table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    out = config.ARTIFACTS / "vocabulary_ablation.csv"
    table.to_csv(out, index=False)
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
