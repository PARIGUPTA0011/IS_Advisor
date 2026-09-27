"""Turning dictated notation back into the notation the index holds.

Speech recognition transcribes what was *said*, and a procurement officer says
an IS number as words: "आई एस सत्रह सौ छियासी" for `IS 1786`, "एफ ई पाँच सौ डी"
for `Fe500D`, "twenty five millimetre" for `25 mm`. None of those spoken forms
matches anything: the citation regex in `Semantic_Analysis/is_advisor/query.py`
wants `IS 1786`, the keyword index holds `Fe500D`, and
`rag/spec_coverage.py` looks for values written the way the dataset writes them.

So this runs on the transcript, before the query layer sees it. Four passes, in
this order, because each depends on the one before:

1. **Digits** - Indic and Arabic-Indic numerals folded to ASCII
   (`multilingual.detect.normalise`), so later passes only see one spelling.
2. **Number words to digits** - "सत्रह सौ छियासी" -> 1786, "seventeen eighty
   six" -> 1786, "twenty five" -> 25.
3. **Spelled letters to acronyms** - "आई एस" -> `IS`, "एफ ई" -> `FE`.
4. **Assembly and units** - the letter runs and numbers next to each other are
   joined the way the dataset joins them (`IS 1786` keeps its space, `Fe500D`
   and `IP66` do not, `DN 150` keeps one), and spoken units become symbols.

**The English letter names are deliberately restricted.** Read literally, "I see
you are here" is the letters I-C-U-R, and a normaliser that believed that would
corrupt ordinary prose. So an ambiguous English letter name ("see", "are",
"you", "why", "eye", "oh", "tea") only counts as a letter when the run it
belongs to is immediately followed by a number, or spells a prefix the dataset
actually uses. "eye ess seventeen eighty six" becomes `IS 1786`; "I see you are
here" is left alone. Devanagari letter names have no such collision - "आई" is
not a Hindi word - so they are accepted unconditionally.

**Coverage is a seed, not a claim.** Hindi and English only, cardinals to 99
plus सौ/हज़ार/लाख, and the unit and prefix tables below. Everything it does not
recognise it leaves exactly as it was, which is the safe direction: an
unconverted "सत्रह सौ" retrieves badly, a wrongly converted one retrieves the
wrong standard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- prefixes, and how the dataset spaces them -------------------------------
#
# Taken from what `multilingual/protect.py` already recognises as notation, so
# the thing this produces is the thing that gets protected across translation.

# "IS 1786", "ISO 9001" - a space, because that is how a citation is written.
CITATION_PREFIXES = {"IS", "ISO", "IEC", "EN", "ASTM", "BS", "DIN", "JIS"}

# "Fe500D", "IP66", "M25" - no space, and with the dataset's own casing.
GLUED_PREFIXES = {
    "FE": "Fe", "IP": "IP", "K": "K", "M": "M", "PE": "PE", "SS": "SS",
    "MS": "MS", "GI": "GI", "DI": "DI", "CI": "CI", "NP": "NP",
    "HDPE": "HDPE", "UPVC": "UPVC", "PVC": "PVC", "XLPE": "XLPE", "FRLS": "FRLS",
}

# "DN 150", "PN 16" - unit-first notation, which keeps its space.
SPACED_PREFIXES = {"DN", "NB", "PN", "AWG", "SWG"}

ALL_PREFIXES = CITATION_PREFIXES | set(GLUED_PREFIXES) | SPACED_PREFIXES

# --- units -------------------------------------------------------------------

UNIT_WORDS: dict[str, str] = {
    # English
    "millimetre": "mm", "millimeter": "mm", "millimetres": "mm", "millimeters": "mm",
    "centimetre": "cm", "centimeter": "cm", "metre": "m", "meter": "m",
    "metres": "m", "meters": "m", "kilometre": "km", "kilometer": "km",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
    "gram": "g", "grams": "g", "tonne": "t", "tonnes": "t", "ton": "t",
    "litre": "L", "liter": "L", "litres": "L", "liters": "L",
    "millilitre": "ml", "milliliter": "ml",
    "watt": "W", "watts": "W", "kilowatt": "kW", "kilowatts": "kW",
    "volt": "V", "volts": "V", "kilovolt": "kV",
    "ampere": "A", "amperes": "A", "amp": "A", "amps": "A",
    "hertz": "Hz", "inch": "inch", "inches": "inch",
    # Hindi
    "मिलीमीटर": "mm", "सेंटीमीटर": "cm", "मीटर": "m", "किलोमीटर": "km",
    "किलोग्राम": "kg", "किलो": "kg", "ग्राम": "g", "टन": "t",
    "लीटर": "L", "मिलीलीटर": "ml",
    "वाट": "W", "किलोवाट": "kW", "वोल्ट": "V", "किलोवोल्ट": "kV",
    "एम्पियर": "A", "एम्पेयर": "A", "हर्ट्ज़": "Hz", "इंच": "inch",
}

# --- letter names ------------------------------------------------------------

# Devanagari letter names. No collisions with ordinary Hindi words, so these are
# accepted wherever they appear.
DEVANAGARI_LETTERS: dict[str, str] = {
    "ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "एफ": "F", "जी": "G",
    "एच": "H", "आई": "I", "जे": "J", "के": "K", "एल": "L", "एम": "M",
    "एन": "N", "ओ": "O", "पी": "P", "क्यू": "Q", "आर": "R", "एस": "S",
    "टी": "T", "यू": "U", "वी": "V", "डब्ल्यू": "W", "डब्लू": "W",
    "एक्स": "X", "वाई": "Y", "ज़ेड": "Z", "जेड": "Z",
}

# Joined forms Whisper often produces instead of separate tokens.
DEVANAGARI_JOINED: dict[str, str] = {
    "आईएस": "IS", "आईएसआई": "ISI", "आईपी": "IP", "एफई": "FE", "डीएन": "DN",
    "एमएस": "MS", "जीआई": "GI", "डीआई": "DI", "पीवीसी": "PVC",
    "एचडीपीई": "HDPE", "यूपीवीसी": "UPVC",
}

# Spoken renderings of a whole prefix that no letter-by-letter table catches.
# Provenance matters here: "fay" is not a guess, it is what Whisper actually
# returned for a speaker saying "F E" in "Fe five hundred D" on this machine.
# Only honoured when a number follows, so the word "Fay" in prose is untouched.
SPOKEN_PREFIX_FORMS: dict[str, str] = {
    "fay": "FE", "eff-ee": "FE", "effie": "FE",
    "eye-ess": "IS", "eyes": "IS",
}

# English letter names that are not also ordinary words.
ENGLISH_LETTERS_SAFE: dict[str, str] = {
    "bee": "B", "cee": "C", "dee": "D", "ef": "F", "eff": "F", "gee": "G",
    "aitch": "H", "haitch": "H", "jay": "J", "kay": "K", "el": "L", "ell": "L",
    "em": "M", "en": "N", "pee": "P", "vee": "V", "ex": "X", "zed": "Z",
    "zee": "Z", "ess": "S", "es": "S",
}

# English letter names that ARE ordinary words. Only honoured next to a number
# or when the run spells a known prefix - see the module docstring.
ENGLISH_LETTERS_AMBIGUOUS: dict[str, str] = {
    "ay": "A", "eye": "I", "see": "C", "oh": "O", "cue": "Q", "queue": "Q",
    "are": "R", "ar": "R", "tea": "T", "tee": "T", "you": "U", "yu": "U",
    "why": "Y", "wy": "Y", "double u": "W",
}

# --- number words ------------------------------------------------------------

ENGLISH_UNITS_0_19 = {
    # "oh" is deliberately not 0 here: it is an interjection and the letter O
    # far more often than a digit, and "oh I see" became "0 I see".
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
ENGLISH_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
ENGLISH_SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100000, "million": 1000000}

# Hindi cardinals. Written out rather than generated because Hindi tens are
# irregular - 86 is छियासी, not a compound of छह and अस्सी - so there is no rule
# to generate them from. Common spelling variants are included where they are
# genuinely common in transcripts (पाँच/पांच, छह/छः).
HINDI_NUMBERS: dict[str, int] = {
    "शून्य": 0, "सिफ़र": 0,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5,
    "छह": 6, "छः": 6, "छे": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "पन्द्रह": 15,
    "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20,
    "इक्कीस": 21, "बाईस": 22, "तेईस": 23, "चौबीस": 24, "पच्चीस": 25,
    "छब्बीस": 26, "सत्ताईस": 27, "अट्ठाईस": 28, "उनतीस": 29, "तीस": 30,
    "इकतीस": 31, "बत्तीस": 32, "तैंतीस": 33, "चौंतीस": 34, "पैंतीस": 35,
    "छत्तीस": 36, "सैंतीस": 37, "अड़तीस": 38, "उनतालीस": 39, "चालीस": 40,
    "इकतालीस": 41, "बयालीस": 42, "तैंतालीस": 43, "चवालीस": 44, "पैंतालीस": 45,
    "छियालीस": 46, "सैंतालीस": 47, "अड़तालीस": 48, "उनचास": 49, "पचास": 50,
    "इक्यावन": 51, "बावन": 52, "तिरपन": 53, "तिरेपन": 53, "चौवन": 54, "पचपन": 55,
    "छप्पन": 56, "सत्तावन": 57, "अट्ठावन": 58, "उनसठ": 59, "साठ": 60,
    "इकसठ": 61, "बासठ": 62, "तिरसठ": 63, "चौंसठ": 64, "पैंसठ": 65,
    "छियासठ": 66, "सड़सठ": 67, "अड़सठ": 68, "उनहत्तर": 69, "सत्तर": 70,
    "इकहत्तर": 71, "बहत्तर": 72, "तिहत्तर": 73, "चौहत्तर": 74, "पचहत्तर": 75,
    "छिहत्तर": 76, "सत्तहत्तर": 77, "अठहत्तर": 78, "उन्यासी": 79, "अस्सी": 80,
    "इक्यासी": 81, "बयासी": 82, "तिरासी": 83, "चौरासी": 84, "पचासी": 85,
    "छियासी": 86, "सत्तासी": 87, "अठासी": 88, "नवासी": 89, "नब्बे": 90,
    "इक्यानवे": 91, "बानवे": 92, "तिरानवे": 93, "चौरानवे": 94, "पंचानवे": 95,
    "छियानवे": 96, "सत्तानवे": 97, "अट्ठानवे": 98, "निन्यानवे": 99,
}
HINDI_SCALES = {"सौ": 100, "हज़ार": 1000, "हजार": 1000, "लाख": 100000}

_WORD_SPLIT_RE = re.compile(r"(\s+)")

# "IS-1786" is what Whisper writes when it hears "IS seventeen eighty six", and
# `is_advisor.query.IS_NUMBER_RE` does not match it - it allows a colon or a dot
# between the prefix and the digits, not a hyphen. So the citation is silently
# lost, the standard is never pinned, and nothing says why. A hyphen between a
# standards prefix and a number is always this artefact; the dataset writes
# "IS 1786".
# "IP 66" is how a transcript writes it and "IP66" is how the dataset does. A
# citation keeps its space ("IS 1786") and so does unit-first notation
# ("DN 150"), so this is a table lookup rather than one rule for every prefix.
#
# Two further restrictions, both learned from getting it wrong. Only *grade and
# rating* prefixes are joined, not the material abbreviations: "GI 25 mm pipe" is
# galvanised iron pipe of 25 mm, and gluing that into "GI25 mm" invents a grade
# and strips the size of its number. And even for these, the digits must not be
# a measurement - "M 25 mm" is a 25 mm something, not grade M25.
GLUE_ON_WRITTEN = ("FE", "IP", "SS", "PE", "NP", "K", "M")

_UNIT_SYMBOLS = (
    "mm|cm|km|kg|mg|ml|kw|kv|hz|m|g|t|l|w|v|a|inch|in|ft|"
    "millimetre|millimeter|centimetre|centimeter|metre|meter|kilogram|gram|"
    "litre|liter|watt|volt|ampere|amp|tonne|ton"
)
_WRITTEN_GLUED_RE = re.compile(
    rf"\b({'|'.join(sorted(GLUE_ON_WRITTEN, key=len, reverse=True))})"
    # The `\b` after the digits stops the engine backtracking `\d+` to a shorter
    # match in order to satisfy the negative lookahead: without it, "M 25 mm"
    # matched by reading only "2", and the unit guard never fired.
    rf"\s+(?=\d+\b(?!\s*(?:{_UNIT_SYMBOLS})\b))",
    re.IGNORECASE,
)

_HYPHENATED_CITATION_RE = re.compile(
    rf"\b({'|'.join(sorted(CITATION_PREFIXES))})\s*[-\u2013\u2014]\s*(?=\d)",
    re.IGNORECASE,
)


@dataclass
class Normalised:
    """The rewritten text, and what was rewritten - so it can be shown, not just trusted."""

    text: str
    original: str = ""
    changes: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.text != self.original

    def summary(self) -> str:
        return ", ".join(f"{before} -> {after}" for before, after in self.changes)


# --- token classification ----------------------------------------------------

def _tokenise(text: str) -> list[str]:
    """Split on whitespace, keeping punctuation attached for later stripping."""
    return [t for t in _WORD_SPLIT_RE.split(text) if t.strip()]


# Punctuation is listed explicitly rather than using `\W`, because Python counts
# Indic vowel signs as non-word characters: `\W` split "सौ" into "स" + "ौ", the
# scale word never matched its lexicon entry, and "सत्रह सौ छियासी" came out as
# "17 सौ छियासी". The hyphen is deliberately absent so hyphenated codes survive.
_PUNCT = r"""[\s.,;:!?'"()\[\]{}/\|<>@#$%^&*~`+=—–…]"""
_EDGE_RE = re.compile(rf"^({_PUNCT}*)(.*?)({_PUNCT}*)$", re.DOTALL)


def _strip_edges(token: str) -> tuple[str, str, str]:
    """Split a token into (leading punctuation, core, trailing punctuation)."""
    match = _EDGE_RE.match(token)
    if not match:
        return "", token, ""
    return match.group(1), match.group(2), match.group(3)


def _number_value(core: str) -> int | None:
    lowered = core.lower()
    if lowered in ENGLISH_UNITS_0_19:
        return ENGLISH_UNITS_0_19[lowered]
    if lowered in ENGLISH_TENS:
        return ENGLISH_TENS[lowered]
    if core in HINDI_NUMBERS:
        return HINDI_NUMBERS[core]
    return None


def _scale_value(core: str) -> int | None:
    lowered = core.lower()
    if lowered in ENGLISH_SCALES:
        return ENGLISH_SCALES[lowered]
    if core in HINDI_SCALES:
        return HINDI_SCALES[core]
    return None


def _letter_value(core: str, allow_ambiguous: bool) -> str | None:
    if core in DEVANAGARI_LETTERS:
        return DEVANAGARI_LETTERS[core]
    lowered = core.lower()
    if lowered in ENGLISH_LETTERS_SAFE:
        return ENGLISH_LETTERS_SAFE[lowered]
    # A bare single Latin letter is always a letter: "I S 1786".
    if len(core) == 1 and core.isascii() and core.isalpha():
        return core.upper()
    if allow_ambiguous and lowered in ENGLISH_LETTERS_AMBIGUOUS:
        return ENGLISH_LETTERS_AMBIGUOUS[lowered]
    return None


# --- number-word runs --------------------------------------------------------

def _read_number(tokens: list[str], start: int) -> tuple[int | None, int]:
    """Read one spoken number starting at `start`. Returns (value, tokens used).

    Three shapes mean three different things, and they have to be told apart
    before any arithmetic happens:

    * **scaled** - "सत्रह सौ छियासी", "one thousand seven hundred eighty six".
      A scale word is present, so it is ordinary place-value arithmetic.
    * **concatenated** - "seventeen eighty six" -> 1786, the way a year or an IS
      number is read aloud. Two groups, each 10..99, no scale word.
    * **digit-by-digit** - "one seven eight six" -> 1786, the other way people
      read a number out. Every group a single digit.

    Anything else is added up. The grouping happens first ("eighty six" is one
    group worth 86) because concatenating before grouping produced 1780 for
    "seventeen eighty six" - it joined 17 and 80 and left the 6 behind.
    """
    # A token that is already digits is one number, taken as-is. It deliberately
    # does not join a multi-group run: "IP 66" and "Fay 500 D" need the digits
    # read, while already-correct text like "25 mm" must come out unchanged, and
    # letting digit tokens concatenate would turn "90 66" into 9066.
    if start < len(tokens):
        _, first_core, _ = _strip_edges(tokens[start])
        if first_core.isdigit():
            return int(first_core), 1

    values: list[int] = []
    scales: list[int] = []
    used = 0
    index = start

    while index < len(tokens):
        _, core, _ = _strip_edges(tokens[index])
        value = _number_value(core)
        scale = _scale_value(core)
        if value is None and scale is None:
            break
        if scale is not None and not values and not scales:
            break                        # a scale word with nothing before it
        values.append(value if value is not None else -scale)
        scales.append(scale or 0)
        used += 1
        index += 1

    if not used:
        return None, 0

    run = [(v, sc) for v, sc in zip(values, scales)]

    # Scaled: place-value arithmetic, left to right.
    if any(scale for _, scale in run):
        total = 0
        current = 0
        for value, scale in run:
            if scale == 0:
                current += value
            elif scale >= 1000:
                total = (total + current) * scale
                current = 0
            else:
                current = (current or 1) * scale
        return total + current, used

    # No scale word: group first, then decide how the groups combine.
    plain = [value for value, _ in run]
    groups: list[int] = []
    position = 0
    while position < len(plain):
        value = plain[position]
        if (
            value in ENGLISH_TENS.values()
            and position + 1 < len(plain)
            and 1 <= plain[position + 1] <= 9
        ):
            groups.append(value + plain[position + 1])       # twenty five -> 25
            position += 2
        else:
            groups.append(value)
            position += 1

    if len(groups) == 1:
        return groups[0], used
    if all(0 <= group <= 9 for group in groups):
        return int("".join(str(group) for group in groups)), used   # one seven eight six
    if all(10 <= group <= 99 for group in groups):
        return int("".join(f"{group:02d}" for group in groups)), used  # seventeen eighty six
    return sum(groups), used


# --- assembly ----------------------------------------------------------------

def _format_code(letters: str, number: str | None, trailing: str) -> str:
    """Join a letter run and an adjacent number the way the dataset writes it."""
    upper = letters.upper()
    if number is None:
        return upper + trailing
    if upper in CITATION_PREFIXES:
        return f"{upper} {number}{trailing}"          # IS 1786
    if upper in SPACED_PREFIXES:
        return f"{upper} {number}{trailing}"          # DN 150
    if upper in GLUED_PREFIXES:
        return f"{GLUED_PREFIXES[upper]}{number}{trailing}"   # Fe500D, IP66
    # Unknown prefix: glue it, which is what an unrecognised grade code looks
    # like, and leave the letters as spoken.
    return f"{upper}{number}{trailing}"


def normalise_spoken_notation(text: str, language: str | None = None) -> Normalised:
    """Rewrite dictated notation into the dataset's written forms.

    `language` is accepted for future per-language rules; the tables are keyed
    by the words themselves, so Hindi and English are both handled whatever is
    passed. Unrecognised input is returned unchanged.
    """
    from multilingual.detect import normalise as normalise_digits

    original = text or ""
    if not original.strip():
        return Normalised(text=original, original=original)

    working = normalise_digits(original)
    # Before tokenising: a hyphen inside a citation is a transcription artefact,
    # and leaving it in costs the citation entirely.
    working = _HYPHENATED_CITATION_RE.sub(lambda match: f"{match.group(1).upper()} ", working)
    working = _WRITTEN_GLUED_RE.sub(
        lambda match: GLUED_PREFIXES[match.group(1).upper()], working
    )
    tokens = _tokenise(working)
    output: list[str] = []
    changes: list[tuple[str, str]] = []
    index = 0

    while index < len(tokens):
        lead, core, trail = _strip_edges(tokens[index])

        # A joined form Whisper produced as one token: "आईएस" -> "IS", or a
        # spoken rendering of a whole prefix: "fay 500 D" -> "Fe500D". The
        # spoken forms need a number after them; the Devanagari ones do not,
        # because they cannot be mistaken for ordinary words.
        spoken_prefix = SPOKEN_PREFIX_FORMS.get(core.lower())
        if spoken_prefix is not None:
            _, follows = _read_number(tokens, index + 1)
            if not follows:
                spoken_prefix = None

        if core in DEVANAGARI_JOINED or spoken_prefix is not None:
            letters = DEVANAGARI_JOINED.get(core) or spoken_prefix or ""
            consumed = [tokens[index]]
            index += 1
            number, used = _read_number(tokens, index)
            if used:
                consumed += tokens[index:index + used]
                index += used
            suffix: list[str] = []
            if used:
                while index < len(tokens):
                    _, suffix_core, _ = _strip_edges(tokens[index])
                    # "D-grade" carries the grade letter and a word; take the
                    # letter and leave the word where it was.
                    head = suffix_core.split("-", 1)[0]
                    suffix_letter = _letter_value(head, allow_ambiguous=False)
                    if suffix_letter is None:
                        break
                    suffix.append(suffix_letter)
                    consumed.append(tokens[index])
                    remainder = suffix_core[len(head):].lstrip("-")
                    index += 1
                    if remainder:
                        tokens.insert(index, remainder)
                        break
                    break
            rendered = lead + _format_code(
                letters, str(number) if used else None, "".join(suffix) + trail
            )
            output.append(rendered)
            changes.append((" ".join(consumed), rendered))
            continue

        # A run of spelled-out letters, optionally followed by a number.
        letters: list[str] = []
        probe = index
        while probe < len(tokens):
            _, probe_core, _ = _strip_edges(tokens[probe])
            letter = _letter_value(probe_core, allow_ambiguous=True)
            if letter is None:
                break
            letters.append(letter)
            probe += 1

        if letters:
            number, used = _read_number(tokens, probe)
            acronym = "".join(letters)
            # An ambiguous English run only counts when a number follows it or
            # it spells a prefix the dataset uses - otherwise "I see you are"
            # would become notation.
            ambiguous = any(
                _letter_value(_strip_edges(tokens[index + offset])[1], allow_ambiguous=False) is None
                for offset in range(len(letters))
            )
            # A one-letter run counts only when it is a known prefix with a
            # number after it - M25, K9 - otherwise a stray "a" before a number
            # would become notation.
            # Letters can also follow the number - "एफ ई पाँच सौ डी" is F, E,
            # 500, then D, and dropping that D turns Fe500D into Fe500, a grade
            # that means something different.
            suffix: list[str] = []
            after = probe + used
            if used:
                while after < len(tokens):
                    _, suffix_core, _ = _strip_edges(tokens[after])
                    suffix_letter = _letter_value(suffix_core, allow_ambiguous=False)
                    if suffix_letter is None:
                        break
                    suffix.append(suffix_letter)
                    after += 1

            # A unit after the number means the number is a measurement, not a
            # grade: "M 25 mm" is a 25 mm something, not grade M25. Same guard as
            # the written-prefix pre-pass, needed again because this path reads
            # spoken numbers rather than digits.
            unit_follows = False
            if used and after < len(tokens):
                _, next_core, _ = _strip_edges(tokens[after])
                unit_follows = bool(
                    UNIT_WORDS.get(next_core) or UNIT_WORDS.get(next_core.lower())
                    or next_core.lower() in {"mm", "cm", "m", "km", "kg", "g", "l", "ml", "w", "v", "a"}
                )
            glue_would_be_wrong = unit_follows and acronym.upper() in GLUED_PREFIXES

            long_enough = len(letters) >= 2 or (used and acronym in ALL_PREFIXES)
            if long_enough and not glue_would_be_wrong and (not ambiguous or used or acronym in ALL_PREFIXES):
                consumed = tokens[index:after]
                _, _, last_trail = _strip_edges(tokens[after - 1])
                rendered = lead + _format_code(
                    acronym, str(number) if used else None, "".join(suffix) + last_trail
                )
                output.append(rendered)
                changes.append((" ".join(consumed), rendered))
                index = after
                continue

        # A spoken number on its own, possibly followed by a spoken unit.
        number, used = _read_number(tokens, index)
        if used:
            consumed = tokens[index:index + used]
            rendered_number = str(number)
            index += used
            if index < len(tokens):
                _, unit_core, unit_trail = _strip_edges(tokens[index])
                unit = UNIT_WORDS.get(unit_core) or UNIT_WORDS.get(unit_core.lower())
                if unit:
                    consumed.append(tokens[index])
                    rendered_number = f"{rendered_number} {unit}{unit_trail}"
                    index += 1
                else:
                    rendered_number += trail
            else:
                rendered_number += trail
            rendered = lead + rendered_number
            output.append(rendered)
            changes.append((" ".join(consumed), rendered))
            continue

        # A spoken unit after a digit that was already written as digits.
        unit = UNIT_WORDS.get(core) or UNIT_WORDS.get(core.lower())
        if unit and output and re.search(r"\d$", output[-1]):
            rendered = lead + unit + trail
            output.append(rendered)
            changes.append((tokens[index], rendered))
            index += 1
            continue

        output.append(tokens[index])
        index += 1

    result = re.sub(r"\s{2,}", " ", " ".join(output)).strip()
    return Normalised(text=result, original=original, changes=changes)
