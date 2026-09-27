"""Build every retrieval artifact from standards.csv.

    python Semantic_Analysis/01_build_index.py            # corpus + BM25 + embeddings
    python Semantic_Analysis/01_build_index.py --no-dense  # corpus + BM25 only (seconds)

Everything lands in Semantic_Analysis/artifacts/ and is reloaded by
is_advisor.search.load_retriever().
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from is_advisor import config, corpus as corpus_mod  # noqa: E402
from is_advisor.lexical import BM25Index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the IS-Advisor retrieval index.")
    parser.add_argument("--no-dense", action="store_true", help="skip embeddings (keyword only)")
    parser.add_argument("--no-past-editions", action="store_true", help="drop mined past-edition vocabulary")
    parser.add_argument("--no-aliases", action="store_true", help="drop the curated trade-name list")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    config.ARTIFACTS.mkdir(parents=True, exist_ok=True)

    start = time.time()
    print("Building corpus from", config.STANDARDS_CSV.name)
    frame = corpus_mod.build_corpus(
        use_past_editions=not args.no_past_editions,
        use_aliases=not args.no_aliases,
    )
    print(f"  {len(frame):,} indexed documents (current + canonical + latest edition)")
    frame.to_parquet(config.CORPUS_PARQUET, index=False)

    lookup = corpus_mod.build_lookup()
    lookup.to_parquet(config.LOOKUP_PARQUET, index=False)
    print(f"  {len(lookup):,} rows in the lookup table (includes withdrawn standards)")

    print("Building BM25 index")
    bm25 = BM25Index(frame["lexical_text"].tolist(), frame["kys_id"].tolist())
    bm25.save()
    print(f"  saved {config.BM25_PICKLE.name}")

    from is_advisor.dense import fingerprint

    doc_fingerprint = fingerprint(frame["doc_text"].tolist())

    if args.no_dense:
        # Embeddings were not rebuilt. They stay valid only while the embedded
        # text is byte-identical, so record whether that still holds.
        previous = json.loads(config.INDEX_META.read_text()) if config.INDEX_META.exists() else {}
        if previous.get("doc_fingerprint") and previous["doc_fingerprint"] != doc_fingerprint:
            print("  ! embedded text changed - existing embeddings.npy is stale, rerun without --no-dense")
        meta = {**previous, "doc_fingerprint": doc_fingerprint, "n_docs": len(frame)}
    else:
        from is_advisor.dense import DenseIndex, encode_documents

        print(f"Embedding {len(frame):,} documents with {config.BI_ENCODER} (CPU)")
        vectors = encode_documents(frame["doc_text"].tolist(), batch_size=args.batch_size)
        index = DenseIndex(vectors)
        index.save()
        print(f"  saved {config.EMBEDDINGS_NPY.name}  shape={vectors.shape}  backend={index.backend}")
        meta = {
            "doc_fingerprint": doc_fingerprint,
            "embedding_fingerprint": doc_fingerprint,
            "n_docs": len(frame),
            "model": config.BI_ENCODER,
        }

    config.INDEX_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"Done in {time.time() - start:.1f}s -> {config.ARTIFACTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
