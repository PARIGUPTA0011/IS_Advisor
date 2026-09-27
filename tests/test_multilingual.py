"""Tests for the multilingual layer. Plain script, no test framework.

    python tests/test_multilingual.py

Every test here runs **without the translation models**. That is deliberate:
these assert the logic the layer is responsible for - which language, which
tokens are protected, what is translated and what is never translated, and
what happens when no model is available - and none of that should depend on a
4.6 GB download or on which checkpoint a machine happens to have.

Where a translation is genuinely needed to exercise a path, a stub engine
stands in (`StubTranslator`), so the real `lift` / `reattach` / glossary /
`unmask` code runs against a deterministic "translation". Model quality is a
separate question, measured by hand in README section 14, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "Semantic_Analysis"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from multilingual import detect as detect_module           # noqa: E402
from multilingual import glossary, languages, localize, protect, translate  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


def check_true(label: str, value) -> None:
    check(label, bool(value), True)


# --- languages --------------------------------------------------------------

def test_registry() -> None:
    print("registry")
    check("22 scheduled languages besides English", len(languages.SCHEDULED_CODES), 22)
    check("iso1 resolves", languages.resolve("hi").code, "hin_Deva")
    check("iso3 resolves", languages.resolve("tam").code, "tam_Taml")
    check("english name resolves", languages.resolve("Marathi").code, "mar_Deva")
    check("flores code resolves", languages.resolve("ory_Orya").name, "Odia")
    check("regional tag resolves", languages.resolve("hi-IN").code, "hin_Deva")
    check("unknown code is not supported", languages.resolve("klingon"), None)
    # An unknown code must not raise: an English answer beats an exception.
    check("unknown falls back to English", languages.get("klingon").code, languages.ENGLISH)
    check("bodo is IndicTrans2-only", "brx_Deva" in languages.INDIC_CODES, True)


# --- detection --------------------------------------------------------------

def test_detection_by_script() -> None:
    print("detection: scripts that admit one answer")
    cases = {
        "தமிழ் கம்பி 500 மிமி": "tam_Taml",
        "ಕನ್ನಡ ಪೈಪ್": "kan_Knda",
        "పైపు మరియు నీరు": "tel_Telu",
        "പൈപ്പ് വെള്ളം": "mal_Mlym",
        "પાણીની ટાંકી": "guj_Gujr",
        "ਪਾਣੀ ਦੀ ਟੈਂਕੀ": "pan_Guru",
        "ପାଣି ଟାଙ୍କି": "ory_Orya",
    }
    for text, expected in cases.items():
        check(f"{expected} from script", detect_module.detect(text).code, expected)


def test_detection_shared_scripts() -> None:
    print("detection: scripts several languages share")
    hindi = detect_module.detect("आरसीसी कार्य के लिये टीएमटी सरिया चाहिये")
    check("hindi in devanagari", hindi.code, "hin_Deva")
    marathi = detect_module.detect("पाणी साठवणुकीसाठी स्टेनलेस स्टील टाकी आहे आणि 500 लिटर")
    check("marathi in devanagari", marathi.code, "mar_Deva")
    check("marker method reported", marathi.method, "script+markers")
    # Devanagari with no marker hit is Hindi: it is the overwhelming prior for
    # procurement text, and guessing a smaller language on no evidence is worse.
    check("bare devanagari defaults to hindi", detect_module.detect("सीमेंट").code, "hin_Deva")

    bengali = detect_module.detect("স্টেইনলেস স্টিল ট্যাঙ্ক প্রয়োজন আর 500 লিটার")
    check("bengali script", bengali.code, "ben_Beng")
    # The Assamese-only letters are a stronger signal than any marker word.
    assamese = detect_module.detect("স্টিল পাইপ লাগিব আৰু 500 লিটাৰ")
    check("assamese by its own letters", assamese.code, "asm_Beng")

    urdu = detect_module.detect("اسٹیل پائپ کی ضرورت ہے")
    check("urdu in arabic script", urdu.code, "urd_Arab")


def test_detection_latin() -> None:
    print("detection: latin script")
    english = detect_module.detect("LED street lights, 90W, 230V AC, outdoor use, IP66 protection.")
    check("english", english.code, languages.ENGLISH)
    check("english is not romanised", english.romanised, False)

    roman = detect_module.detect("TMT sariya Fe500D RCC kaam ke liye chahiye")
    check("romanised hindi", roman.code, "hin_Deva")
    check("romanised flag set", roman.romanised, True)
    check("romanised method reported", roman.method, "romanised")

    # A declared language always wins - a caller who names it knows something
    # the text cannot say, and being wrong about the *output* language is worse.
    declared = detect_module.detect("GI pipes 25mm nominal bore", declared="ta")
    check("declared language wins", (declared.code, declared.method), ("tam_Taml", "declared"))

    # An English tender must not be dragged into translation by one stray word.
    tender = detect_module.detect(
        "Supply of galvanized MS pipes medium class as per IS 1239 Part 1 for the water "
        "distribution network, quantity 500 metres"
    )
    check("english tender stays english", tender.code, languages.ENGLISH)


def test_digits() -> None:
    print("digits")
    check("devanagari digits fold", detect_module.normalise_digits("१२३ mm"), "123 mm")
    check("urdu digits fold", detect_module.normalise_digits("۵۰ kg"), "50 kg")
    check("tamil digits fold", detect_module.normalise_digits("௫௦௦ மிமி"), "500 மிமி")
    check("ascii digits untouched", detect_module.normalise_digits("IS 1786:2008"), "IS 1786:2008")


# --- protection -------------------------------------------------------------

def test_lift_and_reattach() -> None:
    print("protection: into English")
    text = detect_module.normalise("आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786, 500 लिटर")
    lifted = protect.lift(text)
    check("citation lifted", "IS 1786" in lifted.values, True)
    check("grade code lifted", "Fe500D" in lifted.values, True)
    # The number stays inline: lifting it would separate it from its unit, and
    # requirements.py reads a number adjacent to a unit.
    check("number stays in the sentence", "500" in lifted.text, True)
    check("notation removed from the sentence", "Fe500D" in lifted.text, False)

    rebuilt = protect.reattach("TMT bar for RCC work 500 litres", lifted)
    check("citation survives the round trip", "IS 1786" in rebuilt, True)
    check("code survives the round trip", "Fe500D" in rebuilt, True)


def test_mask_and_unmask() -> None:
    print("protection: out of English")
    english = "IS 16107 (Part 2/Sec 2):2017 suits 90W LED luminaires at 230V, IP66."
    masked = protect.mask(english)
    check("citation masked", "IS 16107" in masked.text, False)
    # @1@ rather than a letter form, because NLLB transliterates letters into the
    # target script (PLHA came back as पीएलएचए in Hindi) - see protect.py.
    check("placeholder shape", masked.placeholders[0], "@1@")

    restored, missing = protect.unmask(masked.text, masked)
    check("round trip is exact", restored, english)
    check("nothing missing", missing, [])

    # A model may space a placeholder out, or write its digit in the target
    # script's numerals. It cannot make one mean something, so matching loosely
    # is safe here.
    spaced = masked.text.replace("@1@", "@ 1 @")
    restored, missing = protect.unmask(spaced, masked)
    check("spaced placeholder still resolves", "IS 16107 (Part 2/Sec 2):2017" in restored, True)
    rescripted = masked.text.replace("@1@", "@१@")
    restored, missing = protect.unmask(rescripted, masked)
    check("re-scripted digit still resolves", "IS 16107 (Part 2/Sec 2):2017" in restored, True)

    # A dropped placeholder must not silently drop an IS number.
    dropped = masked.text.replace("@1@", "")
    restored, missing = protect.unmask(dropped, masked)
    check("dropped placeholder is reported", missing, ["IS 16107 (Part 2/Sec 2):2017"])

    # An invented placeholder is never shown to a reader.
    invented, _ = protect.unmask(masked.text + " @9@", masked)
    check("invented placeholder removed", "@9@" in invented, False)


# --- glossary ---------------------------------------------------------------

def test_glossary() -> None:
    print("glossary")
    hints = glossary.hints("टीएमटी सरिया चाहिये", "hin_Deva")
    check("trade term recovered", "TMT" in hints, True)
    # A term the translation already produced is not repeated: a longer
    # document is a document BM25 penalises (README section 7).
    hints = glossary.hints("टीएमटी सरिया", "hin_Deva", already="TMT bar reinforcement steel")
    check("no duplicate hints", hints, [])
    check("wrong language gets nothing", glossary.hints("सरिया", "tam_Taml"), [])
    # A real false positive, found by running the actual translator: "नल" (tap)
    # occurs inside "स्टेनलेस" (stainless), and Indic script offers no word
    # boundary to stop a substring match, so a stainless steel tank was picking
    # up a hint for "tap water fitting". Short terms now match whole tokens only.
    tank = glossary.hints("बाहर लगाने के लिये 500 लिटर की स्टेनलेस स्टील पानी की टंकी", "hin_Deva")
    check("no tap hint from stainless", "tap" in tank, False)
    check("tank hint still found", "tank" in tank, True)
    check("tap still matches as its own word", "tap" in glossary.hints("नल चाहिये", "hin_Deva"), True)
    # A longer term may match an inflected form; that is what the prefix rule is for.
    check("inflected form matches", "tank" in glossary.hints("टंकीयों की जरूरत", "hin_Deva"), True)
    augmented = glossary.augment("rod for concrete", "सरिया", "hin_Deva")
    check("augment is additive", augmented.startswith("rod for concrete"), True)
    check("augment adds the trade term", "TMT" in augmented, True)
    # Romanised terms are in the glossary too, since romanised input is not
    # translated at all.
    check("romanised term recovered", "TMT" in glossary.hints("tmt sariya chahiye", "hin_Deva"), True)


# --- a stub engine, so the plumbing can be tested without a model -----------

class StubBackend:
    """A deterministic 'model'. Substitutes known phrases, tags the rest.

    Deliberately a *backend*, not an override of the translator's own methods:
    everything above it - lifting, masking, batching, the cache, unmasking -
    then runs for real, which is the code these tests exist to check.
    """

    name = "stub"
    PHRASES = {
        "आरसीसी कार्य के लिये टीएमटी सरिया": "TMT bar for RCC work",
        "आरसीसी कार्य के लिये टीएमटी सरिया के अनुसार": "TMT bar for RCC work as per",
        "बाहर लगाने के लिये की स्टेनलेस स्टील पानी की टंकी": "stainless steel water tank for outdoor use",
    }

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    @property
    def reason(self) -> str:
        return ""

    def supports(self, source: str, target: str) -> bool:
        return source != target

    def translate(self, texts, source, target):
        self.calls += 1
        # The fallback deliberately does NOT echo the input. Echoing it made an
        # unknown phrase look like a query-layer bug - Devanagari appearing in
        # the English rendering - when it was only the stub repeating itself.
        return [
            self.PHRASES.get(text.strip(), f"[{target}] untranslated phrase")
            for text in texts
        ]


class StubTranslator(translate.Translator):
    """A translator with both real backends replaced by the stub model."""

    def __init__(self) -> None:
        super().__init__(enabled=True)
        self.backend = StubBackend()
        self._indictrans2 = self.backend
        self._nllb = self.backend

    @property
    def calls(self) -> int:
        return self.backend.calls


def with_stub(function):
    """Install the stub as the process translator for one test."""
    def wrapper():
        previous = translate._DEFAULT
        stub = StubTranslator()
        translate._DEFAULT = stub
        try:
            function(stub)
        finally:
            translate._DEFAULT = previous
    return wrapper


@with_stub
def test_translator_contract(stub) -> None:
    print("translator")
    result = stub.to_english("आरसीसी कार्य के लिये टीएमटी सरिया Fe500D IS 1786")
    check("translated flag set", result.translated, True)
    check("engine reported", result.engine, "stub")
    check("citation preserved", "IS 1786" in result.text, True)
    check("grade code preserved", "Fe500D" in result.text, True)

    english = stub.to_english("LED street light 90W IP66")
    check("english is left alone", english.translated, False)
    check("english reason reported", english.note, "already English")

    roman = stub.to_english("TMT sariya Fe500D chahiye")
    check("romanised is not translated", (roman.translated, roman.note), (False, "romanised"))

    # One model call for a whole tender, not one per line.
    before = stub.calls
    batch = stub.to_english_batch(
        ["आरसीसी कार्य के लिये टीएमटी सरिया", "बाहर लगाने के लिये की स्टेनलेस स्टील पानी की टंकी"]
    )
    check("batch returns one result per input", len(batch), 2)
    check("batch is one model call", stub.calls - before, 1)

    out = stub.from_english("IS 1786 is applicable", "hi")
    check("output direction translated", out.translated, True)
    check("IS number survives the output direction", "IS 1786" in out.text, True)


@with_stub
def test_line_items_carry_both_languages(stub) -> None:
    print("query layer")
    from is_advisor import query

    items = query.parse_document("आरसीसी कार्य के लिये टीएमटी सरिया Fe500D IS 1786 के अनुसार")
    check("one line item", len(items), 1)
    item = items[0]
    check("raw kept as typed", item.raw.startswith("आरसीसी"), True)
    check("english rendering present", "TMT bar" in item.english, True)
    check("language recorded", item.language, "hin_Deva")
    check("translated flag set", item.translated, True)
    check("citation extracted through translation", item.cited_is, ["IS 1786"])
    check("retrieval text is english", "आरसीसी" in item.text, False)

    # multilingual=False must be the old path exactly, which is what the
    # evaluation scripts rely on.
    english_only = query.parse_document("TMT bars Fe500D for RCC work as per IS 1786", multilingual=False)
    check("english-only path unchanged", english_only[0].language, "eng_Latn")
    check("english-only english equals raw", english_only[0].english, english_only[0].raw)
    check("english-only sets no translated flag", english_only[0].translated, False)


@with_stub
def test_indic_key_value_block(stub) -> None:
    print("query layer: labelled blocks in another script")
    from is_advisor import query

    items = query.parse_document("सामग्री: स्टेनलेस स्टील\nक्षमता: 500 लिटर", multilingual=False)
    check("indic keys are recognised as a block", len(items), 1)
    check("both pairs parsed", len(items[0].pairs), 2)
    # And the English pattern still matches exactly what it used to.
    english = query.parse_document("Material: Stainless steel\nCapacity: 200 L", multilingual=False)
    check("english block still one item", len(english), 1)
    check("english pairs still parsed", len(english[0].pairs), 2)


# --- localisation -----------------------------------------------------------

def test_localizer_english_is_a_no_op() -> None:
    print("localisation: English")
    localizer = localize.Localizer(None)
    check("inactive for english", localizer.active, False)
    check("label passes through", localizer.label("Highly relevant").text, "Highly relevant")
    check("text passes through", localizer.plain("matched led, street"), "matched led, street")
    check("no title gloss", localizer.title_gloss("Ordinary portland cement"), None)


def test_localizer_curated_labels() -> None:
    print("localisation: curated labels")
    localizer = localize.Localizer("hi", translator=translate.Translator(enabled=False))
    tier = localizer.label("Highly relevant")
    check("curated tier used", tier.source, "curated")
    check("curated tier text", tier.text, "अत्यधिक प्रासंगिक")
    check("curated status", localizer.label("withdrawn").text, "वापस लिया गया")
    # With no model available, free text must come back as English marked
    # untranslated - never as a blank or a crash.
    free = localizer.text("matched led, street; semantically similar title")
    check("free text falls back to english", free.text, "matched led, street; semantically similar title")
    check("fallback is labelled", free.source, "untranslated")


@with_stub
def test_localise_search_results(stub) -> None:
    print("localisation: ranked results")
    from is_advisor import search

    candidate = search.Candidate(
        kys_id=15491, is_number="IS 8329:2000", title="Ductile iron pressure pipes",
        score=0.97, why="matched ductile, iron", tier="Highly relevant",
    )
    citation = search.CitedStandard(
        cited_as="IS 2062", kys_id=1, is_number="IS 2062:2011", title="Structural steel",
        status="withdrawn", in_index=False, note="cited standard is withdrawn",
    )
    result = search.ItemResult(
        line_item="डक्टाइल आयरन पाइप", query_text="ductile iron pipe",
        candidates=[candidate], cited_standards=[citation],
    )

    search._localise([result], "hin_Deva")
    check("language block attached", result.language["code"], "hin_Deva")
    # The identifier and the official title must be untouched.
    check("is_number untouched", candidate.is_number, "IS 8329:2000")
    check("title untouched", candidate.title, "Ductile iron pressure pipes")
    check("tier localised from the curated table", candidate.tier_localized, "अत्यधिक प्रासंगिक")
    check("why localised", candidate.why_localized.startswith("[hin_Deva]"), True)
    check("title gloss added beside the title", candidate.title_localized is not None, True)
    check("citation note localised", citation.note_localized.startswith("[hin_Deva]"), True)
    check("citation status from curated table", citation.status_localized, "वापस लिया गया")

    payload = result.to_dict()
    check("json carries the language", payload["language"]["code"], "hin_Deva")
    check("json keeps english is_number", payload["candidates"][0]["is_number"], "IS 8329:2000")
    check("json carries localised tier", payload["candidates"][0]["tier_localized"], "अत्यधिक प्रासंगिक")


def test_localise_search_results_english_adds_nothing() -> None:
    print("localisation: English results keep the old contract")
    from is_advisor import search

    candidate = search.Candidate(
        kys_id=1, is_number="IS 269:2015", title="Ordinary portland cement",
        score=0.99, why="matched cement", tier="Highly relevant",
    )
    result = search.ItemResult(line_item="OPC 43 grade", query_text="OPC 43 grade", candidates=[candidate])
    search._localise([result], None)
    payload = result.to_dict()
    check("no language key for english", "language" in payload, False)
    check("no localised keys for english", any(k.endswith("_localized") for k in payload["candidates"][0]), False)
    check("contract keys unchanged", sorted(payload), ["candidates", "cited_standards", "line_item", "query_text", "requirements"])


@with_stub
def test_localise_rag_response(stub) -> None:
    print("localisation: RAG response")
    from rag.pipeline import localise_response
    from rag.response_parser import DirectRecommendation, RecommendationResponse, RelatedStandard

    response = RecommendationResponse(
        query="डक्टाइल आयरन पाइप",
        direct_recommendations=[
            DirectRecommendation(standard_id="IS 8329:2000", reason="Matches ductile iron pipes", status="current")
        ],
        related_standards=[
            RelatedStandard(standard_id="IS 638:1979", relationship="REFERENCES",
                            related_to="IS 8329:2000", reason="Rubber gasket standard")
        ],
        warnings=["One claim was rejected by the grounding validator."],
        confidence="high",
    )
    localise_response(response, "hin_Deva")

    recommendation = response.direct_recommendations[0]
    check("standard_id never translated", recommendation.standard_id, "IS 8329:2000")
    check("reason localised", recommendation.reason_localized.startswith("[hin_Deva]"), True)
    check("english reason kept", recommendation.reason, "Matches ductile iron pipes")
    check("status from curated table", recommendation.status_localized, "वर्तमान")
    check("relationship name stays english", response.related_standards[0].relationship, "REFERENCES")
    check("warnings localised", len(response.warnings_localized), 1)
    check("language block attached", response.language["code"], "hin_Deva")


def test_localise_rag_response_english() -> None:
    print("localisation: English RAG response")
    from rag.pipeline import localise_response
    from rag.response_parser import DirectRecommendation, RecommendationResponse

    response = RecommendationResponse(
        query="ductile iron pipes",
        direct_recommendations=[DirectRecommendation(standard_id="IS 8329:2000", reason="Matches", status="current")],
        confidence="high",
    )
    localise_response(response, None)
    check("nothing localised", response.direct_recommendations[0].reason_localized, None)
    check("language reported as english", response.language["code"], languages.ENGLISH)
    check("english needs no localisation", response.language["localized"], False)


# --- retrieval-side guards --------------------------------------------------

def test_tokenizer_keeps_every_script() -> None:
    print("keyword index tokenizer")
    from is_advisor.lexical import tokenize

    check("english unchanged", tokenize("LED Street Lighting Luminaire"), ["led", "street", "lighting", "luminaire"])
    # Before this change the pattern was [a-z0-9]+, so a Devanagari query
    # tokenised to its digits and a Tamil one to nothing at all.
    check("devanagari survives", tokenize("टीएमटी सरिया"), ["टीएमटी", "सरिया"])
    check("tamil survives", tokenize("கம்பி"), ["கம்பி"])
    check("urdu survives", len(tokenize("اسٹیل پائپ")), 2)
    check("digits still tokenise", tokenize("IS 16107 Part 2"), ["16107", "part", "2"])


def test_stale_vectors_detect_an_encoder_swap() -> None:
    print("stale-vector guard")
    import json
    import tempfile

    import pandas as pd

    from is_advisor import config, search
    from is_advisor.dense import fingerprint

    frame = pd.DataFrame({"doc_text": ["a document"]})
    original = config.INDEX_META
    # Written to a temporary path, never to artifacts/: a real build may be
    # running, and a test that restores a file it did not write would undo it.
    with tempfile.TemporaryDirectory() as directory:
        config.INDEX_META = Path(directory) / "index_meta.json"
        try:
            # Same text, different encoder. The fingerprint cannot see this -
            # the text did not change - and the vectors are the right shape
            # with the wrong meaning.
            # Any encoder that is not the configured one. Derived rather than
            # hardcoded: this test used to name bge-small-en-v1.5 explicitly and
            # silently stopped testing anything the day config.BI_ENCODER became
            # that model.
            other_encoder = (
                "some-other/encoder" if config.BI_ENCODER != "some-other/encoder"
                else "yet-another/encoder"
            )
            config.INDEX_META.write_text(
                json.dumps({
                    "model": other_encoder,
                    "embedding_fingerprint": fingerprint(frame["doc_text"].tolist()),
                    "n_docs": 1,
                }),
                encoding="utf-8",
            )
            check("encoder swap is caught", search._embeddings_are_stale(frame), True)

            config.INDEX_META.write_text(
                json.dumps({
                    "model": config.BI_ENCODER,
                    "embedding_fingerprint": fingerprint(frame["doc_text"].tolist()),
                    "n_docs": 1,
                }),
                encoding="utf-8",
            )
            check("matching encoder and text is not stale", search._embeddings_are_stale(frame), False)

            config.INDEX_META.write_text(
                json.dumps({
                    "model": config.BI_ENCODER,
                    "embedding_fingerprint": "text has since changed",
                    "n_docs": 1,
                }),
                encoding="utf-8",
            )
            check("changed document text is still caught", search._embeddings_are_stale(frame), True)
        finally:
            config.INDEX_META = original


def main() -> int:
    test_registry()
    test_detection_by_script()
    test_detection_shared_scripts()
    test_detection_latin()
    test_digits()
    test_lift_and_reattach()
    test_mask_and_unmask()
    test_glossary()
    test_translator_contract()
    test_line_items_carry_both_languages()
    test_indic_key_value_block()
    test_localizer_english_is_a_no_op()
    test_localizer_curated_labels()
    test_localise_search_results()
    test_localise_search_results_english_adds_nothing()
    test_localise_rag_response()
    test_localise_rag_response_english()
    test_tokenizer_keeps_every_script()
    test_stale_vectors_detect_an_encoder_swap()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all multilingual checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
