"""Tests for the spoken-notation normaliser.

    python tests/test_speech_notation.py

No audio, no model: this is pure text in, text out. That is the point of having
it as a separate pass - the part most likely to be wrong is the part that needs
no 460 MB download to check.

The cases below are the ones the feature exists for, plus the ones that would
make it dangerous: ordinary prose that happens to contain English letter names
("I see you are here"), and input that is already written correctly and must
come out untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from speech.notation import normalise_spoken_notation  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


def norm(text: str) -> str:
    return normalise_spoken_notation(text).text


# --- the cases the feature exists for ----------------------------------------

def test_hindi_is_number() -> None:
    print("Hindi IS number")
    check("spelled letters + scaled number", norm("आई एस सत्रह सौ छियासी"), "IS 1786")
    check("joined letter form", norm("आईएस सत्रह सौ छियासी"), "IS 1786")
    check("thousand form", norm("आई एस एक हज़ार सात सौ छियासी"), "IS 1786")
    check("inside a sentence",
          norm("मुझे आई एस सत्रह सौ छियासी चाहिये"), "मुझे IS 1786 चाहिये")


def test_hindi_grade_code() -> None:
    print("Hindi grade code")
    check("Fe500D", norm("एफ ई पाँच सौ डी"), "Fe500D")
    check("spelling variant पांच", norm("एफ ई पांच सौ डी"), "Fe500D")
    check("M25", norm("एम पच्चीस"), "M25")


def test_numbers_with_units() -> None:
    print("numbers with units")
    check("25 mm", norm("पच्चीस मिलीमीटर"), "25 mm")
    check("English 25 mm", norm("twenty five millimetre"), "25 mm")
    check("500 litre", norm("पाँच सौ लीटर"), "500 L")
    check("90 watt", norm("ninety watts"), "90 W")
    check("unit after written digits", norm("25 millimetre"), "25 mm")


def test_english_is_number() -> None:
    print("English IS number")
    # "eye ess" is how it is said; both names are ordinary English words, so this
    # is exactly the case the number-follows guard is there to permit.
    check("eye ess + year form", norm("eye ess seventeen eighty six"), "IS 1786")
    check("single letters", norm("I S seventeen eighty six"), "IS 1786")
    check("IP rating", norm("eye pee sixty six"), "IP66")
    check("DN keeps its space", norm("dee en one hundred fifty"), "DN 150")


def test_year_style_versus_additive() -> None:
    print("number shapes")
    # Two tens-words in a row is a year ("seventeen eighty six" = 1786); a tens
    # word plus a unit word is additive ("twenty five" = 25). Getting these the
    # same way round would turn 25 mm into 2005 mm.
    check("concatenated", norm("seventeen eighty six"), "1786")
    check("additive", norm("twenty five"), "25")
    check("scaled", norm("five hundred"), "500")
    check("Hindi scaled", norm("सत्रह सौ छियासी"), "1786")
    check("Hindi additive", norm("पच्चीस"), "25")


# --- the cases that would make it dangerous ----------------------------------

def test_digit_by_digit_dictation() -> None:
    print("digit-by-digit")
    # The other way people read a number aloud. Every group a single digit, so
    # it concatenates rather than summing - "one seven eight six" is 1786, not 22.
    check("English digits", norm("eye ess one seven eight six"), "IS 1786")
    check("Hindi digits", norm("आई एस एक सात आठ छह"), "IS 1786")
    check("bare digit string", norm("one seven eight six"), "1786")


def test_transcription_artefacts_from_a_real_run() -> None:
    print("artefacts a real transcript produced")
    # Every case here came out of Whisper on this machine, not from imagination.
    # "IS-1786" is the important one: is_advisor.query.IS_NUMBER_RE allows a colon
    # or a dot between the prefix and the digits but not a hyphen, so the citation
    # was silently lost and the standard never got pinned.
    check("hyphenated citation", norm("IS-1786 TMT bars"), "IS 1786 TMT bars")
    check("spaced hyphen", norm("IS - 1786"), "IS 1786")
    # "Fay" is what Whisper returned for a speaker saying "F E".
    check("spoken Fe prefix", norm("Fay 500 D"), "Fe500D")
    check("full real transcript",
          norm("IS-1786 TMT reinforcement bars, Fay 500 D-grade, 25 mm diameter"),
          "IS 1786 TMT reinforcement bars, Fe500D grade 25 mm diameter")
    # The word Fay with no number after it is a name, not a grade.
    check("Fay as a word", norm("the Fay family lives here"), "the Fay family lives here")


def test_written_prefixes_are_glued_only_when_right() -> None:
    print("gluing written prefixes")
    # The dataset writes IP66 and SS304, so a transcript's "IP 66" should join.
    check("IP 66", norm("IP 66"), "IP66")
    check("SS 304", norm("SS 304"), "SS304")
    check("M 25", norm("M 25"), "M25")
    # But a material abbreviation followed by a measurement must not: "GI 25 mm"
    # is galvanised iron pipe of 25 mm, and "GI25 mm" invents a grade and strips
    # the size of its number.
    check("GI stays apart", norm("GI 25 mm pipe"), "GI 25 mm pipe")
    check("DI stays apart", norm("DI 300 mm pipe"), "DI 300 mm pipe")
    check("grade prefix + measurement stays apart", norm("M 25 mm"), "M 25 mm")
    # Citations and unit-first notation keep their spaces either way.
    check("citation keeps space", norm("IS 1786"), "IS 1786")
    check("DN keeps space", norm("DN 150"), "DN 150")


def test_ordinary_english_prose_is_left_alone() -> None:
    print("ordinary prose")
    # Read as letters this is I-C-U-R. A normaliser that believed that would
    # corrupt every English sentence containing these words.
    check("I see you are here", norm("I see you are here"), "I see you are here")
    check("why are you", norm("why are you asking"), "why are you asking")
    check("oh I see", norm("oh I see"), "oh I see")


def test_already_written_notation_is_untouched() -> None:
    print("already correct input")
    for text in (
        "IS 1786",
        "LED street lights, 90W, 230V AC, outdoor use, IP66 protection.",
        "Fe500D TMT bars conforming to IS 1786:2008",
        "GI pipes 25 mm nominal bore",
    ):
        check(f"unchanged: {text[:34]}", norm(text), text)


def test_unrecognised_input_passes_through() -> None:
    print("unrecognised input")
    check("Tamil left alone", norm("கம்பி தேவை"), "கம்பி தேவை")
    check("empty", norm(""), "")
    check("whitespace only", normalise_spoken_notation("   ").text, "   ")


def test_indic_digits_are_folded() -> None:
    print("Indic digits")
    check("devanagari digits", norm("१२३ मिलीमीटर"), "123 mm")
    check("mixed", norm("आई एस १७८६"), "IS 1786")


# --- reporting ---------------------------------------------------------------

def test_changes_are_reported() -> None:
    print("what changed is visible")
    result = normalise_spoken_notation("आई एस सत्रह सौ छियासी")
    check("marked as changed", result.changed, True)
    check("original kept", result.original, "आई एस सत्रह सौ छियासी")
    check("one rewrite recorded", len(result.changes), 1)
    check("summary reads correctly", result.summary(), "आई एस सत्रह सौ छियासी -> IS 1786")
    untouched = normalise_spoken_notation("IS 1786")
    check("no changes on clean input", untouched.changed, False)


def main() -> int:
    test_hindi_is_number()
    test_hindi_grade_code()
    test_numbers_with_units()
    test_english_is_number()
    test_year_style_versus_additive()
    test_digit_by_digit_dictation()
    test_transcription_artefacts_from_a_real_run()
    test_written_prefixes_are_glued_only_when_right()
    test_ordinary_english_prose_is_left_alone()
    test_already_written_notation_is_untouched()
    test_unrecognised_input_passes_through()
    test_indic_digits_are_folded()
    test_changes_are_reported()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all spoken-notation checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
