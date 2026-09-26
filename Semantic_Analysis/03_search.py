"""Query the index and emit the ranked candidates the knowledge graph consumes.

    python Semantic_Analysis/03_search.py "TMT bars Fe500D for RCC work"
    python Semantic_Analysis/03_search.py --file tender.txt --json out.json
    python Semantic_Analysis/03_search.py --file tender.pdf
    echo "..." | python Semantic_Analysis/03_search.py --json -

A query in any of the 22 scheduled Indian languages is answered in that same
language; the language is detected unless `--lang` names it:

    python Semantic_Analysis/03_search.py "\u0906\u0930\u0938\u0940\u0938\u0940 \u0915\u093e\u0930\u094d\u092f \u0915\u0947 \u0932\u093f\u092f\u0947 \u091f\u0940\u090f\u092e\u091f\u0940 \u0938\u0930\u093f\u092f\u093e"
    python Semantic_Analysis/03_search.py --file tender_hi.txt --lang hi
    python Semantic_Analysis/03_search.py "GI pipes 25mm" --lang ta   # English in, Tamil out

Output is one record per line item, in the shape agreed with the graph
workstream: a line item, its candidates, and any standards it cited outright.
IS numbers and official titles are always the English originals; localised
strings sit beside them in `*_localized` fields.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiet_warnings  # noqa: E402

quiet_warnings.apply()

# A Windows console defaults to cp1252, which cannot encode Devanagari, Tamil
# or Arabic script: printing a localised answer there raises
# UnicodeEncodeError and loses the whole result. Reconfiguring stdout is the
# fix; `errors="replace"` keeps a terminal that genuinely cannot render a
# script showing boxes rather than failing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):                 # pragma: no cover
        pass

from is_advisor import config  # noqa: E402
from is_advisor.documents import ScannedPdfError, read_document  # noqa: E402
from is_advisor.search import load_retriever, tier_for  # noqa: E402


def _render_requirements(requirements) -> list[str]:
    """Show what was understood before showing what was found."""
    if requirements is None or requirements.is_empty():
        return []
    lines = ["  understood:"]
    if requirements.product:
        lines.append(f"      product      {requirements.product}")
    for label, values in (("material", requirements.material),
                          ("environment", requirements.environment),
                          ("properties", requirements.properties)):
        if values:
            lines.append(f"      {label:12s} {', '.join(values)}")
    for quantity in requirements.quantities:
        span = f"{quantity.value:g}" + (f" to {quantity.value_max:g}" if quantity.value_max else "")
        qualifier = f"{quantity.qualifier} " if quantity.qualifier else ""
        lines.append(f"      {quantity.field or 'value':12s} {qualifier}{span} {quantity.unit}")
    if requirements.unmapped:
        lines.append(f"      {'unmapped':12s} {'; '.join(requirements.unmapped[:3])}")
    return lines


def render(results) -> str:
    lines = []
    for result in results:
        lines.append(f"\n{'=' * 78}\nLINE ITEM  {result.line_item.strip()[:74]}")
        if result.language:
            language = result.language
            lines.append(f"  language: {language['name']} ({language['code']})")
            if result.line_item_english:
                lines.append(f"  english : {result.line_item_english[:70]}")
        lines.append(f"  searched: {result.query_text[:70]}")
        lines.extend(_render_requirements(result.requirements))
        for citation in result.cited_standards:
            status = citation.status_localized or citation.status or "unknown"
            note = citation.note_localized or citation.note
            lines.append(f"  cited {citation.cited_as} [{status}] {note}")
            if citation.replaced_by_is:
                lines.append(f"        replaced by {citation.replaced_by_is}")
        if not result.candidates:
            lines.append("  no candidates")
            continue
        current_tier = None
        for rank, candidate in enumerate(result.candidates, 1):
            tier = candidate.tier_localized or candidate.tier or tier_for(candidate.score)
            if tier != current_tier:
                lines.append(f"  -- {tier} --")
                current_tier = tier
            cert = "  [cert]" if candidate.mandatory_cert else ""
            lines.append(
                f"  {rank:2d}. {candidate.score:.3f}  {candidate.is_number:24s} {candidate.title[:52]}{cert}"
            )
            # The official English title stays on the line above, because that
            # is what goes into a tender document. The gloss is a reading aid.
            if candidate.title_localized:
                lines.append(f"        {candidate.title_localized[:74]}")
            lines.append(f"        why: {(candidate.why_localized or candidate.why)[:78]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommend Indian Standards for a specification.")
    parser.add_argument("text", nargs="*", help="specification text")
    parser.add_argument("--file", type=Path, help="read the specification from a .txt or .pdf file")
    parser.add_argument("--json", help="write JSON results here ('-' for stdout)")
    parser.add_argument("--top-k", type=int, default=5)
    # Off by default: on the current evaluation set the cross-encoder lowers
    # Recall@5 and costs about six times the latency. See README.
    parser.add_argument("--rerank", action="store_true", help="enable cross-encoder reranking")
    parser.add_argument("--no-dense", action="store_true", help="keyword-only retrieval")
    parser.add_argument(
        "--lang",
        help="input and output language (ISO or FLORES code, e.g. hi, ta, hin_Deva); "
             "detected from the text when omitted",
    )
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="English-only path: no detection, no translation, no localised output",
    )
    args = parser.parse_args()

    if args.file:
        try:
            document = read_document(args.file)
        except ScannedPdfError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    elif args.text:
        document = " ".join(args.text)
    elif not sys.stdin.isatty():
        document = sys.stdin.read()
    else:
        parser.error("give a specification as an argument, --file, or on stdin")

    if not config.CORPUS_PARQUET.exists():
        parser.error(f"no index found at {config.ARTIFACTS} - run 01_build_index.py first")

    retriever = load_retriever(with_dense=not args.no_dense, with_reranker=args.rerank)
    results = retriever.search_document(
        document,
        top_k=args.top_k,
        use_reranker=args.rerank,
        language=args.lang,
        multilingual=False if args.no_translate else None,
    )

    payload = [r.to_dict() for r in results]
    if args.json == "-":
        # ensure_ascii=False so a localised answer is readable in the JSON too,
        # rather than a wall of \uXXXX escapes.
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render(results))
        if args.json:
            Path(args.json).write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
