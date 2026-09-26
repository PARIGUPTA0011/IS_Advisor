"""
Quick manual test runner for the RAG pipeline.

Usage:
    python run_query.py "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."
    python run_query.py "90W LED street light IP66" --lang hi
    python run_query.py "\u0938\u0921\u093c\u0915 \u0915\u0940 \u092c\u0924\u094d\u0924\u0940 90W IP66"

The language is detected from the query; `--lang` (ISO or FLORES code) forces
it, which is also how to ask an English question and read the answer in
another language.
"""

import sys

# Before the model stack is imported, so its import-time warnings are caught.
# See quiet_warnings.py for what is hidden and why; IS_ADVISOR_ALL_WARNINGS=1
# brings it all back.
import quiet_warnings

quiet_warnings.apply()

# A Windows console is cp1252 and cannot encode Indic scripts, so printing a
# localised answer would raise UnicodeEncodeError instead of answering.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):                 # pragma: no cover
        pass

from rag.metadata_store import MetadataStore
from rag.kg_client import Neo4jKGClient
from rag.llm_client import get_llm_client
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python run_query.py "your query here" [--lang hi]')
        sys.exit(1)

    query = sys.argv[1]
    language = None
    if "--lang" in sys.argv:
        index = sys.argv.index("--lang")
        if index + 1 >= len(sys.argv):
            print("--lang needs a language code, for example --lang hi")
            sys.exit(1)
        language = sys.argv[index + 1]

    store = MetadataStore()
    retriever = get_retriever(store)
    kg = Neo4jKGClient.from_env()
    llm = get_llm_client()

    # One sentence, once, instead of a notification block per missing label and
    # property on every query. The driver's own notifications are turned off in
    # kg_client.py; set NEO4J_NOTIFICATIONS=1 to see them again.
    warning = kg.empty_graph_warning()
    if warning:
        print(f"! {warning}\n", file=sys.stderr)

    try:
        result = run_query(query, retriever, store, kg, llm, top_k=5, language=language)
    finally:
        kg.close()

    print("QUERY:", query)
    if result.response.query_english:
        print("ENGLISH:", result.response.query_english)
    if result.detection:
        detection = result.detection
        print(f"LANGUAGE: {detection['name']} ({detection['code']}) "
              f"by {detection['method']}, confidence {detection['confidence']}")
    if result.translation and result.translation.get("note"):
        print("TRANSLATION:", result.translation["engine"], "-", result.translation["note"])
    print()
    print("CONFIDENCE:", result.response.confidence)
    print()
    print("DIRECT RECOMMENDATIONS:")
    for r in result.response.direct_recommendations:
        print(f"  - {r.standard_id} (status={r.status_localized or r.status}) [{r.evidence_tag}]")
        print(f"    reason: {r.reason_localized or r.reason}")
        if r.reason_localized:
            print(f"    english: {r.reason}")
    print()
    print("RELATED STANDARDS:")
    for r in result.response.related_standards:
        marker = " [WITHDRAWN]" if (r.status or "").lower() == "withdrawn" else ""
        print(f"  - {r.standard_id} --{r.relationship}--> {r.related_to}{marker}")
        if r.title:
            print(f"    covers: {r.title}")
        print(f"    reason: {r.reason_localized or r.reason}")
    print()
    if result.response.unsupported_spec_terms:
        print("SPEC VALUES NOT CONFIRMED BY EVIDENCE:",
              ", ".join(result.response.unsupported_spec_terms))
    print()
    print("WARNINGS:", result.response.warnings_localized or result.response.warnings)
    print()
    print("RETRIEVED EVIDENCE:")
    for e in result.evidence:
        title = e.record.title if e.record else "?"
        is_number = e.record.is_number if e.record else "?"
        print(f"  kys_id={e.kys_id} score={e.score:.4f} {is_number}  {title[:70]}")


if __name__ == "__main__":
    main()
