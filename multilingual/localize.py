"""Answering in the language the question arrived in.

The standards corpus is English - 33,803 of 35,524 rows are marked English,
120 bilingual and 17 Hindi - so a same-language answer is *produced*, never
looked up. That splits the output into three kinds of text, handled
differently on purpose:

1. **Identifiers - never translated.** `IS 1786`, `IS 16107 (Part 2/Sec 2):2017`.
   A translated identifier is a broken identifier.
2. **Official titles - kept, with a gloss.** "Ordinary portland cement -
   Specification" is the standard's name; a procurement officer quoting it in
   a tender must quote the English. So the English title stays, and a machine
   translation is offered *beside* it as `title_localized`, marked as a gloss.
3. **Everything the pipeline itself wrote - translated.** The `why` string,
   the citation note, the LLM's `reason` and `warnings`, field labels, tier
   names. This is the text that exists to be read, and it is the whole point
   of the feature.

Field labels and tier names go through a curated table where one exists, and
through the translation model otherwise, because two words out of context is
where MT is weakest and where a wrong word is most visible. Hindi is curated;
every other language falls back to the model, and `source` on the result says
which happened.

Order matters, and it is not negotiable: **localisation runs last**, after the
RAG grounding validator. The validator matches IS numbers and clause patterns
in English text (`rag/grounding_validator.py`), so translating before it would
hand it prose it cannot check. Everything that enforces correctness sees
English; only what is displayed is translated.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config, languages
from .languages import ENGLISH
from .translate import Translator, get_translator

# --- curated labels ---------------------------------------------------------
#
# Keys are the English strings the pipelines already emit, so a caller does not
# have to learn a second vocabulary. Hindi is curated because it is the
# dominant non-English case for Indian procurement; the rest are translated by
# the model and cached, which the status field reports as "mt".

_CURATED: dict[str, dict[str, str]] = {
    "hin_Deva": {
        # tiers (Semantic_Analysis/is_advisor/config.py)
        "Highly relevant": "अत्यधिक प्रासंगिक",
        "Related": "संबंधित",
        "Possibly relevant": "संभवतः प्रासंगिक",
        # statuses
        "current": "वर्तमान",
        "withdrawn": "वापस लिया गया",
        # requirement fields (is_advisor/requirements.py)
        "product": "उत्पाद",
        "material": "सामग्री",
        "environment": "वातावरण",
        "properties": "गुण",
        "quantities": "मात्रा",
        "unmapped": "अवर्गीकृत",
        # display labels
        "understood": "समझा गया",
        "searched": "खोजा गया",
        "why": "कारण",
        "cited": "उद्धृत",
        "no candidates": "कोई परिणाम नहीं",
        "recommendations": "सिफ़ारिशें",
        "related standards": "संबंधित मानक",
        "warnings": "चेतावनियाँ",
        "confidence": "विश्वास स्तर",
        "line item": "मद",
        "title": "शीर्षक",
        "machine translation": "मशीनी अनुवाद",
    },
}


@dataclass(frozen=True)
class Localized:
    """One piece of localised text, and where it came from."""

    text: str
    source: str = "original"     # original | curated | mt | untranslated
    english: str = ""

    def __str__(self) -> str:                       # convenient in f-strings
        return self.text


class Localizer:
    """Localises one response into one target language.

    Construct per request (cheap - the translator and its cache are shared),
    so that `target` never has to be threaded through every call.
    """

    def __init__(self, target: str | None, translator: Translator | None = None):
        self.language = languages.get(target)
        self.target = self.language.code
        self.translator = translator or get_translator()

    @property
    def active(self) -> bool:
        """False when the target is English and there is nothing to do."""
        return self.target != ENGLISH

    # --- pieces of text -----------------------------------------------------

    def label(self, english: str) -> Localized:
        """A short UI label or enum value: curated table first, model second."""
        if not self.active or not english:
            return Localized(english, "original", english)
        curated = _CURATED.get(self.target, {}).get(english)
        if curated:
            return Localized(curated, "curated", english)
        return self.text(english)

    def text(self, english: str | None) -> Localized:
        """A sentence the pipeline wrote, for a human to read."""
        if not english:
            return Localized(english or "", "original", english or "")
        if not self.active:
            return Localized(english, "original", english)
        result = self.translator.from_english(english, self.target)
        if not result.translated:
            return Localized(english, "untranslated", english)
        return Localized(result.text, "mt", english)

    def title_gloss(self, title: str | None) -> Localized | None:
        """A translation offered *beside* an official title, never replacing it."""
        if not title or not self.active or not config.TRANSLATE_TITLES:
            return None
        gloss = self.text(title)
        return gloss if gloss.source == "mt" else None

    def prime(self, english_strings: list[str | None]) -> None:
        """Translate everything a response needs, in one model call.

        Call this with every string about to be localised. It translates the
        unique, uncurated ones as a single batch and leaves them in the
        translator cache, so the per-field `label`/`text`/`title_gloss` calls
        that follow are cache lookups. Without it, a five-candidate answer
        makes a dozen sequential model calls on CPU, which is where the latency
        of a localised response would otherwise all come from.
        """
        if not self.active:
            return
        curated = _CURATED.get(self.target, {})
        unique: list[str] = []
        for item in english_strings:
            if not item or item in curated or item in unique:
                continue
            unique.append(item)
        if unique:
            self.translator.batch_from_english(unique, self.target)

    # --- convenience --------------------------------------------------------

    def texts(self, items: list[str] | None) -> list[Localized]:
        return [self.text(item) for item in (items or [])]

    def plain(self, english: str | None) -> str:
        """`text()` when the caller only wants the string."""
        return self.text(english).text

    def plain_label(self, english: str) -> str:
        return self.label(english).text

    def describe(self) -> dict:
        """What a response should say about its own language handling."""
        return {
            "code": self.target,
            "name": self.language.name,
            "native_name": self.language.native_name,
            "tier": self.language.tier,
            "localized": self.active,
            "titles_translated": bool(self.active and config.TRANSLATE_TITLES),
            "note": (
                "IS numbers and official titles are kept in English; translated "
                "text is machine translation"
                if self.active else ""
            ),
        }
