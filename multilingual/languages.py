"""The language registry: what "multilingual" means here, concretely.

Two tiers, because they behave differently and a caller needs to know which
one it got:

* **First class** - the 22 languages of the Eighth Schedule of the Indian
  Constitution, plus English. These have a script, a known IndicTrans2 code,
  detection rules in `detect.py`, and localised field labels in `localize.py`.
  IndicTrans2 is the strongest open model for these, and it is the only one
  that covers Bodo, Dogri, Konkani and Santali at all (verified by probing the
  installed NLLB tokenizer, not read off a model card).
* **Best effort** - anything else the installed NLLB checkpoint happens to
  support. Detection for these is weaker (see `detect.py`), nothing is
  hand-curated, and every response says so via the language's `tier`.

Codes are FLORES-200 style (`hin_Deva`), which is what both IndicTrans2 and
NLLB-200 use, so one code serves both backends. The short ISO-639-1 code is
what an API caller is likely to send (`"hi"`), so both resolve.
"""

from __future__ import annotations

from dataclasses import dataclass

ENGLISH = "eng_Latn"

TIER_FIRST_CLASS = "first_class"
TIER_BEST_EFFORT = "best_effort"


@dataclass(frozen=True)
class Language:
    code: str                 # FLORES-200 code, e.g. "hin_Deva"
    name: str                 # English name
    native_name: str          # endonym, for echoing back to the user
    script: str               # Unicode script name used by detect.py
    iso1: str | None = None   # ISO-639-1, what API callers usually send
    iso3: str | None = None   # ISO-639-3
    indictrans2: bool = True  # covered by the IndicTrans2 checkpoints
    tier: str = TIER_FIRST_CLASS

    @property
    def is_english(self) -> bool:
        return self.code == ENGLISH


# --- the 22 scheduled languages, plus English -------------------------------
#
# Script assignments follow what the language is predominantly written in
# today, not what it could be written in. Three are genuinely dual-script;
# detect.py maps a script to a language rather than the reverse, so Kashmiri
# written in Devanagari is reported as Kashmiri only when its own marker words
# appear - otherwise Devanagari means Hindi, which is the safer default.

_SCHEDULED: tuple[Language, ...] = (
    Language("eng_Latn", "English", "English", "Latin", "en", "eng"),
    Language("asm_Beng", "Assamese", "অসমীয়া", "Bengali", "as", "asm"),
    Language("ben_Beng", "Bengali", "বাংলা", "Bengali", "bn", "ben"),
    Language("brx_Deva", "Bodo", "बड़ो", "Devanagari", None, "brx"),
    Language("doi_Deva", "Dogri", "डोगरी", "Devanagari", None, "doi"),
    Language("gom_Deva", "Konkani", "कोंकणी", "Devanagari", "kok", "gom"),
    Language("guj_Gujr", "Gujarati", "ગુજરાતી", "Gujarati", "gu", "guj"),
    Language("hin_Deva", "Hindi", "हिन्दी", "Devanagari", "hi", "hin"),
    Language("kan_Knda", "Kannada", "ಕನ್ನಡ", "Kannada", "kn", "kan"),
    Language("kas_Arab", "Kashmiri", "کٲشُر", "Arabic", "ks", "kas"),
    Language("mai_Deva", "Maithili", "मैथिली", "Devanagari", None, "mai"),
    Language("mal_Mlym", "Malayalam", "മലയാളം", "Malayalam", "ml", "mal"),
    Language("mni_Beng", "Manipuri", "মৈতৈলোন্", "Bengali", None, "mni"),
    Language("mar_Deva", "Marathi", "मराठी", "Devanagari", "mr", "mar"),
    Language("npi_Deva", "Nepali", "नेपाली", "Devanagari", "ne", "npi"),
    Language("ory_Orya", "Odia", "ଓଡିଆ", "Oriya", "or", "ory"),
    Language("pan_Guru", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi", "pa", "pan"),
    Language("san_Deva", "Sanskrit", "संस्कृतम्", "Devanagari", "sa", "san"),
    Language("sat_Olck", "Santali", "ᱥᱟᱱᱛᱱᱟᱲᱤ", "Ol_Chiki", None, "sat"),
    Language("snd_Arab", "Sindhi", "سنڌي", "Arabic", "sd", "snd"),
    Language("tam_Taml", "Tamil", "தமிழ்", "Tamil", "ta", "tam"),
    Language("tel_Telu", "Telugu", "తెలుగు", "Telugu", "te", "tel"),
    Language("urd_Arab", "Urdu", "اُردُو", "Arabic", "ur", "urd"),
)

# Manipuri also has its own script (Meetei Mayek). IndicTrans2 ships the
# Bengali-script variant, so Meetei Mayek input is reported as Manipuri and
# translated through mni_Beng. Recorded here rather than silently mapped.
MEETEI_MAYEK_FALLBACK = "mni_Beng"

# --- best-effort languages --------------------------------------------------
#
# Deliberately short. These are the non-Indian languages a procurement query
# plausibly arrives in (donor-funded and export tenders). Each is used only if
# the installed NLLB checkpoint really carries the code - translate.py probes
# the tokenizer rather than trusting this table.

_BEST_EFFORT: tuple[Language, ...] = (
    Language("arb_Arab", "Arabic", "العربية", "Arabic", "ar", "ara", False, TIER_BEST_EFFORT),
    Language("deu_Latn", "German", "Deutsch", "Latin", "de", "deu", False, TIER_BEST_EFFORT),
    Language("fra_Latn", "French", "Français", "Latin", "fr", "fra", False, TIER_BEST_EFFORT),
    Language("ind_Latn", "Indonesian", "Bahasa Indonesia", "Latin", "id", "ind", False, TIER_BEST_EFFORT),
    Language("jpn_Jpan", "Japanese", "日本語", "Japanese", "ja", "jpn", False, TIER_BEST_EFFORT),
    Language("kor_Hang", "Korean", "한국어", "Hangul", "ko", "kor", False, TIER_BEST_EFFORT),
    Language("pes_Arab", "Persian", "فارسی", "Arabic", "fa", "fas", False, TIER_BEST_EFFORT),
    Language("por_Latn", "Portuguese", "Português", "Latin", "pt", "por", False, TIER_BEST_EFFORT),
    Language("rus_Cyrl", "Russian", "Русский", "Cyrillic", "ru", "rus", False, TIER_BEST_EFFORT),
    Language("spa_Latn", "Spanish", "Español", "Latin", "es", "spa", False, TIER_BEST_EFFORT),
    Language("swh_Latn", "Swahili", "Kiswahili", "Latin", "sw", "swh", False, TIER_BEST_EFFORT),
    Language("tha_Thai", "Thai", "ไทย", "Thai", "th", "tha", False, TIER_BEST_EFFORT),
    Language("vie_Latn", "Vietnamese", "Tiếng Việt", "Latin", "vi", "vie", False, TIER_BEST_EFFORT),
    Language("zho_Hans", "Chinese (Simplified)", "简体中文", "Han", "zh", "zho", False, TIER_BEST_EFFORT),
)

ALL: tuple[Language, ...] = _SCHEDULED + _BEST_EFFORT

BY_CODE: dict[str, Language] = {lang.code: lang for lang in ALL}
SCHEDULED_CODES: frozenset[str] = frozenset(
    lang.code for lang in _SCHEDULED if not lang.is_english
)
INDIC_CODES: frozenset[str] = frozenset(lang.code for lang in _SCHEDULED if lang.indictrans2)

# Every spelling a caller might send, resolved to one FLORES code. Built from
# the registry so a new language needs one row and nothing else.
_ALIASES: dict[str, str] = {}
for _lang in ALL:
    for _key in (_lang.code, _lang.iso1, _lang.iso3, _lang.name):
        if _key:
            _ALIASES[_key.lower()] = _lang.code
_ALIASES.update({
    "english": ENGLISH, "en-in": ENGLISH, "en_us": ENGLISH, "en-us": ENGLISH,
    "hindi": "hin_Deva", "hi-in": "hin_Deva",
    "bangla": "ben_Beng", "oriya": "ory_Orya", "odiya": "ory_Orya",
    "panjabi": "pan_Guru", "gurmukhi": "pan_Guru",
    "manipuri": "mni_Beng", "meitei": "mni_Beng", "meiteilon": "mni_Beng",
    "konkani": "gom_Deva", "nepalese": "npi_Deva",
    "zh": "zho_Hans", "zh-cn": "zho_Hans", "cmn": "zho_Hans",
    # Romanised Indic input is still that language; detect.py returns these
    # codes with method="romanised" so a caller can tell how it was decided.
    "hinglish": "hin_Deva", "roman_hindi": "hin_Deva",
})


def resolve(code: str | None) -> Language | None:
    """Look up a language by FLORES code, ISO code, English name or alias."""
    if not code:
        return None
    key = str(code).strip().lower().replace(" ", "_").replace("-", "-")
    flores = _ALIASES.get(key)
    if flores is None and "_" in key:           # "hin_deva" -> "hin_Deva"
        flores = _ALIASES.get(key.split("_")[0])
    if flores is None and "-" in key:           # "hi-IN" -> "hi"
        flores = _ALIASES.get(key.split("-")[0])
    return BY_CODE.get(flores) if flores else None


def get(code: str | None) -> Language:
    """Like `resolve`, but falls back to English rather than returning None.

    A caller that reaches here with an unknown code is better served by an
    English answer it can read than by an exception, and the fallback is
    always reported in the response.
    """
    return resolve(code) or BY_CODE[ENGLISH]


def name_of(code: str | None) -> str:
    return get(code).name


def is_supported(code: str | None) -> bool:
    return resolve(code) is not None
