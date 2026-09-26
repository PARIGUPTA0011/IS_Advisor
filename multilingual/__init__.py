"""Multilingual input and output for IS-Advisor.

The whole layer sits at the *edges* of the existing pipelines and changes
nothing in the middle. A query arrives in any of the 22 scheduled Indian
languages (or a best-effort other language), is normalised and translated into
English, and from there runs through exactly the retrieval, knowledge-graph
and grounding code that was measured in English. The answer is then translated
back into the language it was asked in.

    query (any language)
      -> detect.detect          script-first, marker words for shared scripts
      -> detect.normalise       NFC + Indic digits folded to ASCII
      -> protect.lift           IS numbers and grade codes taken out of harm's way
      -> translate.to_english   IndicTrans2, or NLLB-200
      -> glossary.augment       native trade terms -> English trade terms
      ==> the existing English pipeline, untouched
      -> localize.Localizer     answer translated back, identifiers left alone

Two invariants hold everywhere in here, and both exist to protect correctness
that was established in English:

1. **Retrieval, grounding and validation only ever see English.** Localisation
   is the last step, after `rag/grounding_validator.py` has done its work.
2. **Identifiers are never translated.** `IS 1786` stays `IS 1786`; official
   titles stay English and get a translated gloss beside them.

Nothing here needs an API key, and nothing reaches the network after the first
model download. `translate.py` degrades to returning the original text rather
than failing when no checkpoint is available, so an install without the MT
models keeps working exactly as the English-only pipeline did.
"""

# `detect` the function is deliberately re-exported as `detect_language`: a
# top-level name `detect` would shadow the `multilingual.detect` submodule in
# this package's namespace, so `import multilingual.detect` would hand a caller
# the function instead of the module.
from .detect import Detection, normalise, normalise_digits, script_profile
from .detect import detect as detect_language
from .glossary import augment as augment_with_glossary
from .languages import ALL as ALL_LANGUAGES
from .languages import ENGLISH, SCHEDULED_CODES, Language
from .languages import get as get_language
from .languages import resolve as resolve_language
from .localize import Localized, Localizer
from .translate import Translation, Translator, detect_and_translate, get_translator

__all__ = [
    "ALL_LANGUAGES",
    "Detection",
    "ENGLISH",
    "Language",
    "Localized",
    "Localizer",
    "SCHEDULED_CODES",
    "Translation",
    "Translator",
    "augment_with_glossary",
    "detect_and_translate",
    "detect_language",
    "get_language",
    "get_translator",
    "normalise",
    "normalise_digits",
    "resolve_language",
    "script_profile",
]


def prepare_query(text: str, language: str | None = None) -> tuple[Detection, Translation, str]:
    """Everything the query side needs, in one call.

    Returns the detection, the translation, and the English query text with
    glossary hints appended - which is what retrieval should actually run on.
    """
    detection, translation = detect_and_translate(text, language)
    english = augment_with_glossary(translation.text, text or "", detection.code)
    return detection, translation, english
