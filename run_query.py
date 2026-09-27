"""
Quick manual test runner for the RAG pipeline.

Usage:
    python run_query.py "LED street lights, 90W, 230V AC, outdoor use, IP66 protection."
    python run_query.py "90W LED street light IP66" --lang hi
    python run_query.py --audio query.m4a              # wav/mp3/m4a, transcribed locally
    python run_query.py --mic 8                        # record 8 seconds and ask that
    python run_query.py "\u0938\u0921\u093c\u0915 \u0915\u0940 \u092c\u0924\u094d\u0924\u0940 90W IP66"

The language is detected from the query; `--lang` forces it, which is also how
to ask an English question and read the answer in another language. Any of
three spellings works - a plain name (`--lang Hindi`), an ISO code
(`--lang hi`) or a FLORES-200 code (`--lang hin_Deva`) - so the value the
frontend sends and the value typed here are interchangeable.
"""

import argparse
import sys
from pathlib import Path

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
from rag.kg_client import get_kg_client
from rag.llm_client import get_llm_client
from rag.pipeline import run_query
from rag.retriever_factory import get_retriever


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask IS-Advisor for the standards that apply to a specification.",
    )
    parser.add_argument("text", nargs="*", help="the query, as text")
    parser.add_argument(
        "--lang",
        help="language of the question and the answer: a name (Hindi), an ISO code "
             "(hi) or a FLORES code (hin_Deva). Detected when omitted; with --audio "
             "or --mic it also overrides what Whisper heard",
    )
    parser.add_argument(
        "--audio", type=Path,
        help="transcribe this audio file and ask that (wav/mp3/m4a, transcribed "
             "locally with faster-whisper - no API, no upload)",
    )
    parser.add_argument(
        "--mic", type=float, metavar="SECONDS",
        help="record this many seconds from the microphone and ask that",
    )
    args = parser.parse_args()

    language = args.lang
    typed = " ".join(args.text).strip()

    if args.audio and args.mic:
        parser.error("use either --audio or --mic, not both")
    if not (typed or args.audio or args.mic):
        parser.error("give a query as text, or --audio FILE, or --mic SECONDS")

    query = typed
    if args.audio or args.mic:
        # The speech layer is imported here rather than at module scope so that a
        # text-only run never pays for it, and an install without faster-whisper
        # keeps working exactly as before.
        from speech import SpeechUnavailable, render_transcript, transcribe
        from speech.record import MicrophoneUnavailable

        try:
            transcript = transcribe(
                audio_path=args.audio, mic_seconds=args.mic, language=language
            )
        except (SpeechUnavailable, MicrophoneUnavailable, FileNotFoundError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            sys.exit(2)

        # Printed before anything else: the transcript is the least reliable link
        # in the chain and the only one a user can check at a glance.
        print(render_transcript(transcript))
        print()
        if not transcript.ok:
            print(f"error: {transcript.note or 'nothing was transcribed'}", file=sys.stderr)
            sys.exit(2)

        query = f"{transcript.text} {typed}".strip() if typed else transcript.text
        # Whisper's language, already checked against the transcript's script.
        language = language or transcript.language

    store = MetadataStore()
    retriever = get_retriever(store)
    kg = get_kg_client()
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
        print(f"  kys_id={e.kys_id} score={e.score:.4f} tier={e.tier}  {is_number}  {title[:70]}")
        if e.why:
            print(f"    why: {e.why}")


if __name__ == "__main__":
    main()
