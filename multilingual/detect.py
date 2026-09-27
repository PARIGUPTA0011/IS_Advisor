"""Which language did the officer type in?

Detection here is script-first and deliberately not a single model call, for
one reason that matters in this dataset: **the script is decisive for every
Indian language except the ones that share a script.** Tamil text can only be
Tamil. Gujarati can only be Gujarati. A statistical language identifier adds
nothing there but a way to be wrong, so Unicode ranges decide those, and
marker words only break the ties the script genuinely leaves open:

* Devanagari - Hindi, Marathi, Nepali, Sanskrit, Maithili, Konkani, Bodo, Dogri
* Bengali script - Bengali, Assamese, Manipuri
* Arabic script - Urdu, Kashmiri, Sindhi (and Persian/Arabic, best effort)
* Latin - English, romanised Indic ("Hinglish"), other Latin-script languages

Two honest limits, both reported rather than hidden:

1. **Romanised Indic is detected, not resolved well.** "TMT sariya 500D chahiye"
   is recognisably not English, and recognisably Hindi-family, but telling
   romanised Hindi from romanised Marathi by marker words is unreliable, so a
   low confidence comes back with it. `Detection.romanised` is set, and the
   retrieval side deliberately does *not* machine-translate romanised input -
   it already retrieves well through the curated trade names in
   `Semantic_Analysis/data/aliases.csv`, and running it through MT would risk
   a measured-good path for an unmeasured one.
2. **Latin-script non-English** (French, Spanish, ...) is guessed from small
   function-word tables, or from `langdetect` when that package is installed.
   These are best-effort languages anyway.

A caller who knows the language should say so; a declared language always wins
and is reported as `method="declared"`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import languages
from .languages import ENGLISH, Language

# --- script ranges ----------------------------------------------------------
#
# One entry per script we can name. Ranges are inclusive. Anything not listed
# is counted as "other" and never decides the outcome on its own.

_SCRIPT_RANGES: tuple[tuple[str, int, int], ...] = (
    ("Devanagari", 0x0900, 0x097F),
    ("Devanagari", 0xA8E0, 0xA8FF),          # Devanagari Extended
    ("Bengali", 0x0980, 0x09FF),
    ("Gurmukhi", 0x0A00, 0x0A7F),
    ("Gujarati", 0x0A80, 0x0AFF),
    ("Oriya", 0x0B00, 0x0B7F),
    ("Tamil", 0x0B80, 0x0BFF),
    ("Telugu", 0x0C00, 0x0C7F),
    ("Kannada", 0x0C80, 0x0CFF),
    ("Malayalam", 0x0D00, 0x0D7F),
    ("Ol_Chiki", 0x1C50, 0x1C7F),
    ("Meetei_Mayek", 0xABC0, 0xABFF),
    ("Meetei_Mayek", 0xAAE0, 0xAAFF),        # Meetei Mayek Extensions
    ("Arabic", 0x0600, 0x06FF),
    ("Arabic", 0x0750, 0x077F),
    ("Arabic", 0xFB50, 0xFDFF),
    ("Arabic", 0xFE70, 0xFEFF),
    ("Cyrillic", 0x0400, 0x04FF),
    ("Thai", 0x0E00, 0x0E7F),
    ("Japanese", 0x3040, 0x30FF),            # hiragana + katakana
    ("Hangul", 0x1100, 0x11FF),
    ("Hangul", 0x3130, 0x318F),
    ("Hangul", 0xAC00, 0xD7AF),
    ("Han", 0x3400, 0x4DBF),
    ("Han", 0x4E00, 0x9FFF),
    ("Latin", 0x0041, 0x005A),
    ("Latin", 0x0061, 0x007A),
    ("Latin", 0x00C0, 0x024F),               # Latin-1 letters + Extended A/B
)

# One script per language for the scripts that admit exactly one answer.
_SCRIPT_TO_LANGUAGE: dict[str, str] = {
    "Gurmukhi": "pan_Guru",
    "Gujarati": "guj_Gujr",
    "Oriya": "ory_Orya",
    "Tamil": "tam_Taml",
    "Telugu": "tel_Telu",
    "Kannada": "kan_Knda",
    "Malayalam": "mal_Mlym",
    "Ol_Chiki": "sat_Olck",
    "Meetei_Mayek": languages.MEETEI_MAYEK_FALLBACK,
    "Cyrillic": "rus_Cyrl",
    "Thai": "tha_Thai",
    "Japanese": "jpn_Jpan",
    "Hangul": "kor_Hang",
    "Han": "zho_Hans",
}

# An Indic-script query routinely carries English fragments - "IS 1786",
# "Fe500D", "IP66", "DN 150" - so the script that decides does not have to be
# the majority script, only a real presence. The reverse case (a Devanagari
# fragment inside an otherwise English tender) is rare, and mis-routing it
# costs only a needless translation of text that is already English.
_INDIC_SHARE_FLOOR = 0.10

# --- marker words for the shared scripts ------------------------------------
#
# Function words and copulas only: content words are shared across these
# languages far more than grammar is. Each list is short on purpose - a long
# list drifts into words the neighbouring language also uses, which is exactly
# the failure a marker table is supposed to avoid.

_DEVANAGARI_MARKERS: dict[str, tuple[str, ...]] = {
    "hin_Deva": ("है", "हैं", "का", "की", "के",
                 "को", "लिये", "लिए", "और",
                 "में", "नहीं", "होगा",
                 "क्या", "इस", "उस", "वाला"),
    "mar_Deva": ("आहे", "आणि", "साठी", "च्या",
                 "ची", "चे", "मध्ये", "नाही",
                 "पाहिजे", "असलेल्या"),
    "npi_Deva": ("छ", "छन्", "लागि", "र", "पर्छ",
                 "गर्ने", "भयो"),
    "san_Deva": ("अस्ति", "च", "इति", "भवति",
                 "एव", "तथा"),
    "mai_Deva": ("अडि", "अछि", "लेल", "केँ"),
    "gom_Deva": ("आसा", "आनी", "खातीर",
                 "जाल्यार"),
    "brx_Deva": ("आरो", "थाखाय", "बुं",
                 "गोनां"),
    "doi_Deva": ("हैगा", "गीं", "देंदे"),
}

_BENGALI_MARKERS: dict[str, tuple[str, ...]] = {
    "ben_Beng": ("আর", "করা", "হবে", "জন্য",
                 "আছে", "এবং", "নয়", "কি"),
    "asm_Beng": ("আৰু", "হয়", "কৰি", "লাগিব",
                 "আছে"),
    "mni_Beng": ("অমসুং", "মখোয়", "কোয়",
                 "ওইরিবা"),
}

# Assamese uses two letters Bengali does not: ra with middle diagonal (U+09F0)
# and wa (U+09F1). Their presence is a stronger signal than any marker word.
_ASSAMESE_ONLY_CHARS = "ৰৱ"

# Sindhi and Kashmiri carry Arabic-script letters Urdu does not use.
_SINDHI_ONLY_CHARS = "ٻڀٿٽڦڻڱڳڇڄ"
_KASHMIRI_ONLY_CHARS = "ۆۄݜٲٳ"

_ARABIC_SCRIPT_MARKERS: dict[str, tuple[str, ...]] = {
    "urd_Arab": ("ہے", "کے", "اور", "کۓ", "کا",
                 "کی", "لیہ", "میں", "چاہیے"),
    "snd_Arab": ("اڳي", "جي", "هتي", "احم"),
    "pes_Arab": ("است", "برای", "و", "می‌شود"),
    "arb_Arab": ("هو", "ذلك", "في", "من", "على"),
}

# --- romanised Indic --------------------------------------------------------
#
# Tokens that are common in romanised Indian-language procurement text and are
# not English words. Words that collide with English ("me", "to", "par", "so")
# are left out even where they are frequent, because a false positive here
# sends an English query down the translation path.

_ROMANISED_MARKERS: dict[str, frozenset[str]] = {
    "hin_Deva": frozenset("""
        ka ki ke kaa kii liye lie hai hain hei hona hoga chahiye chahiyay chaahiye
        aur ya se mein kya kyon kaise kitna kitne kitni nahi nahin yeh woh wala wali wale
        iske uske jarurat zaroorat jaruri zaroori banane banwana lagana kharidna khareedna
        saman samagri kaam sariya gitti balu reti bijli paani tanki makan dukan sadak
        chhota bada naya purana accha achha behtar sasta mehenga
    """.split()),
    "mar_Deva": frozenset("""
        aahe ahe aani ani sathi saathi chya chi che madhe nahi pahije paahije
        asleli karaycha havi hava lagnar
    """.split()),
    "ben_Beng": frozenset("""
        ache achhe ebong jonno jonno korte hobe amar tomar kintu tahole
        khub bhalo lagbe dorkar
    """.split()),
}

# Counter-evidence: if the text reads as English, these turn up thick and fast.
_ENGLISH_FUNCTION_WORDS = frozenset("""
    the a an and or of for with to in on at by from as is are be been shall must
    should will not no any each per than that this these those it its their there
    required supply supplied provide provided make made used using type grade
""".split())

# Small tables for the Latin-script best-effort languages, used only when
# `langdetect` is not installed.
_LATIN_OTHER_MARKERS: dict[str, frozenset[str]] = {
    "fra_Latn": frozenset("le la les des une pour avec dans est sont doit nous vous cette".split()),
    "spa_Latn": frozenset("el la los las una para con del que son debe este esta".split()),
    "por_Latn": frozenset("o a os as uma para com dos que sao deve este esta nao".split()),
    "deu_Latn": frozenset("der die das und mit fur ist sind muss eine einen nicht".split()),
    "ind_Latn": frozenset("dan yang untuk dengan adalah harus ini itu dari pada".split()),
    "vie_Latn": frozenset("va cua cho voi la phai nay khong trong duoc".split()),
    "swh_Latn": frozenset("na ya kwa katika ni lazima hii hiyo kwa ajili".split()),
}

# Splitting on punctuation and whitespace rather than matching `\w+`, because
# Python's `\w` excludes Indic combining vowel marks (they are category Mn and
# not alphanumeric), which silently cut every Devanagari word at its first
# matra and made the marker tables below unmatchable.
_SPLIT_RE = re.compile(r"[\s,;:.()\[\]/\|\"'!?%+*=<>@#&~`{}^_–—-]+", re.UNICODE)


@dataclass(frozen=True)
class Detection:
    """What was decided, and on what basis - both are part of the answer."""

    code: str                              # FLORES-200 code
    confidence: float                      # 0..1, heuristic, never a probability
    method: str                            # declared | script | script+markers | romanised | langdetect | default
    script: str = "Latin"
    romanised: bool = False                # Indic language written in Latin letters
    scripts: dict[str, float] = field(default_factory=dict)   # share of letters per script

    @property
    def language(self) -> Language:
        return languages.get(self.code)

    @property
    def is_english(self) -> bool:
        return self.code == ENGLISH

    def to_dict(self) -> dict:
        lang = self.language
        return {
            "code": self.code,
            "name": lang.name,
            "native_name": lang.native_name,
            "script": self.script,
            "tier": lang.tier,
            "romanised": self.romanised,
            "confidence": round(float(self.confidence), 3),
            "method": self.method,
        }


def script_profile(text: str) -> dict[str, float]:
    """Share of the text's letters belonging to each named script."""
    counts: dict[str, int] = {}
    total = 0
    for char in text or "":
        if not char.isalpha():
            continue
        total += 1
        code_point = ord(char)
        name = "other"
        for script, low, high in _SCRIPT_RANGES:
            if low <= code_point <= high:
                name = script
                break
        counts[name] = counts.get(name, 0) + 1
    if not total:
        return {}
    return {script: count / total for script, count in sorted(counts.items(), key=lambda kv: -kv[1])}


def tokens_of(text: str) -> list[str]:
    """Word tokens, split on punctuation and whitespace, combining marks kept.

    Public because the glossary needs exactly this notion of a token: matching
    its terms as raw substrings finds "नल" (tap) inside "स्टेनलेस"
    (stainless), and no script-specific word boundary exists to prevent it.
    """
    return [token for token in _SPLIT_RE.split(text or "") if token]


def _tokens(text: str) -> list[str]:
    """Lowercased word tokens, digits dropped, for the marker tables."""
    return [token.lower() for token in tokens_of(text) if not token.isdigit()]


def _best_by_markers(text: str, table: dict[str, tuple[str, ...]]) -> tuple[str | None, int]:
    """Language whose marker words appear most often, and the hit count."""
    tokens = _tokens(text)
    if not tokens:
        return None, 0
    counted = {
        code: sum(1 for token in tokens if token in set(markers))
        for code, markers in table.items()
    }
    best = max(counted, key=lambda code: counted[code])
    return (best, counted[best]) if counted[best] else (None, 0)


def _resolve_devanagari(text: str) -> tuple[str, str, float]:
    code, hits = _best_by_markers(text, _DEVANAGARI_MARKERS)
    if code and hits:
        # Nepali's marker set is two very short words; one hit is not enough
        # to outrank Hindi, which is the overwhelming prior for Devanagari
        # procurement text.
        if code != "hin_Deva" and hits < 2:
            return "hin_Deva", "script", 0.6
        return code, "script+markers", min(0.65 + 0.1 * hits, 0.95)
    return "hin_Deva", "script", 0.7


def _resolve_bengali_script(text: str) -> tuple[str, str, float]:
    if any(char in _ASSAMESE_ONLY_CHARS for char in text):
        return "asm_Beng", "script+markers", 0.9
    code, hits = _best_by_markers(text, _BENGALI_MARKERS)
    if code and hits:
        return code, "script+markers", min(0.7 + 0.1 * hits, 0.95)
    return "ben_Beng", "script", 0.75


def _resolve_arabic_script(text: str) -> tuple[str, str, float]:
    if any(char in _SINDHI_ONLY_CHARS for char in text):
        return "snd_Arab", "script+markers", 0.85
    if any(char in _KASHMIRI_ONLY_CHARS for char in text):
        return "kas_Arab", "script+markers", 0.8
    code, hits = _best_by_markers(text, _ARABIC_SCRIPT_MARKERS)
    if code and hits:
        return code, "script+markers", min(0.65 + 0.1 * hits, 0.9)
    return "urd_Arab", "script", 0.6


def _langdetect(text: str) -> str | None:
    """Ask `langdetect` if it is installed. Optional by design: it is only
    consulted for Latin-script text, where the script rules have nothing to
    say, and it is poor at romanised Indic, which is handled before this."""
    try:
        from langdetect import DetectorFactory, detect        # type: ignore

        DetectorFactory.seed = 0
        guess = detect(text)
    except Exception:
        return None
    resolved = languages.resolve(guess)
    return resolved.code if resolved else None


def _resolve_latin(text: str) -> tuple[str, str, float, bool]:
    """English, romanised Indic, or another Latin-script language."""
    tokens = _tokens(text)
    if not tokens:
        return ENGLISH, "default", 0.3, False

    english_hits = sum(1 for token in tokens if token in _ENGLISH_FUNCTION_WORDS)

    romanised_counts = {
        code: sum(1 for token in tokens if token in markers)
        for code, markers in _ROMANISED_MARKERS.items()
    }
    best_romanised = max(romanised_counts, key=lambda code: romanised_counts[code])
    romanised_hits = romanised_counts[best_romanised]

    # Two markers, or one in a short query, and no stronger English signal.
    # Procurement English is dense in function words, so `english_hits` is a
    # real counterweight rather than a formality.
    enough = romanised_hits >= 2 or (romanised_hits == 1 and len(tokens) <= 6)
    if enough and romanised_hits >= english_hits:
        share = romanised_hits / len(tokens)
        return best_romanised, "romanised", min(0.45 + share, 0.8), True

    guess = _langdetect(text)
    if guess and guess != ENGLISH:
        return guess, "langdetect", 0.7, False
    if guess == ENGLISH:
        return ENGLISH, "langdetect", 0.8, False

    other_counts = {
        code: sum(1 for token in tokens if token in markers)
        for code, markers in _LATIN_OTHER_MARKERS.items()
    }
    best_other = max(other_counts, key=lambda code: other_counts[code])
    if other_counts[best_other] >= 2 and other_counts[best_other] > english_hits:
        return best_other, "script+markers", 0.55, False

    return ENGLISH, "script", 0.8 if english_hits else 0.6, False


def detect(text: str, declared: str | None = None) -> Detection:
    """Identify the language of `text`.

    `declared` is whatever the caller asked for (an API field, a `--lang`
    flag). It always wins, because a caller who names the language knows
    something the text cannot tell us - and a wrong guess on output language
    is more annoying than a wrong guess on input language.
    """
    if declared:
        resolved = languages.resolve(declared)
        if resolved is not None:
            return Detection(
                code=resolved.code,
                confidence=1.0,
                method="declared",
                script=resolved.script,
                scripts=script_profile(text),
            )

    profile = script_profile(text)
    if not profile:
        return Detection(ENGLISH, 0.3, "default", "Latin", scripts=profile)

    # An Indic script only needs a real presence, not a majority: the English
    # technical fragments in an Indic query would otherwise outvote it.
    indic_scripts = [
        (script, share) for script, share in profile.items()
        if script not in {"Latin", "other"} and share >= _INDIC_SHARE_FLOOR
    ]
    if indic_scripts:
        script = max(indic_scripts, key=lambda item: item[1])[0]
        if script == "Devanagari":
            code, method, confidence = _resolve_devanagari(text)
        elif script == "Bengali":
            code, method, confidence = _resolve_bengali_script(text)
        elif script == "Arabic":
            code, method, confidence = _resolve_arabic_script(text)
        else:
            code = _SCRIPT_TO_LANGUAGE.get(script)
            if code is None:
                return Detection(ENGLISH, 0.3, "default", script, scripts=profile)
            method, confidence = "script", 0.95
        return Detection(code, confidence, method, script, scripts=profile)

    code, method, confidence, romanised = _resolve_latin(text)
    return Detection(code, confidence, method, "Latin", romanised=romanised, scripts=profile)


# --- digits -----------------------------------------------------------------
#
# Every Indic script has its own digits, and a procurement query carries
# numbers that decide the answer ("90W", "IP66", "DN 150"). Requirement
# extraction and citation matching are both regex over ASCII digits, so
# Indic digits have to be folded before either runs, whatever happens to the
# words around them.

_DIGIT_TRANSLATION = {}
for _base in (
    0x0966,  # Devanagari
    0x09E6,  # Bengali
    0x0A66,  # Gurmukhi
    0x0AE6,  # Gujarati
    0x0B66,  # Oriya
    0x0BE6,  # Tamil
    0x0C66,  # Telugu
    0x0CE6,  # Kannada
    0x0D66,  # Malayalam
    0x0660,  # Arabic-Indic
    0x06F0,  # Extended Arabic-Indic (Urdu, Persian)
    0x1C50,  # Ol Chiki
    0xABF0,  # Meetei Mayek
):
    for _offset in range(10):
        _DIGIT_TRANSLATION[_base + _offset] = ord(str(_offset))


def normalise_digits(text: str) -> str:
    """Fold Indic and Arabic-Indic digits to ASCII, leaving letters alone."""
    return (text or "").translate(_DIGIT_TRANSLATION)


def digit_variants(digit: str) -> str:
    """Every Unicode spelling of one ASCII digit, including the ASCII one.

    `protect.py` needs this to find its placeholders again: a translation into
    Urdu or Hindi may render the digit inside a placeholder in the target
    script's own numerals, which is a reformatting the model is entitled to do
    and which a plain string search would miss.
    """
    return digit + "".join(
        chr(code_point)
        for code_point, ascii_code in _DIGIT_TRANSLATION.items()
        if ascii_code == ord(digit)
    )


def normalise(text: str) -> str:
    """NFC-normalise and fold digits. Cheap, and safe on English input.

    NFC matters for Indic text because the same syllable can arrive
    pre-composed or decomposed, and a marker-word lookup that compares
    strings would miss the decomposed spelling.
    """
    return normalise_digits(unicodedata.normalize("NFC", text or ""))
