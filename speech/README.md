# Speech input

Dictate a query instead of typing it. This is an **edge layer**, in exactly the
sense `multilingual/` is: audio becomes text at the edge, and retrieval, the
knowledge graph, the prompt, the LLM and the grounding validator receive a
string, as they always did. Nothing downstream knows a microphone was involved.

```
audio (file or microphone)
  ↓  record.py            optional: --mic SECONDS, via sounddevice
  ↓  transcribe.py        faster-whisper `small`, CPU, offline after first download
  ↓  notation.py          "आई एस सत्रह सौ छियासी" → "IS 1786"; "पच्चीस मिलीमीटर" → "25 mm"
  ↓  reconcile_language   Whisper's guess checked against the transcript's script
  ════════════════════    the existing text pipeline, unchanged
  multilingual.prepare_query → retrieval → KG → LLM → validate → localise
```

```bash
python run_query.py --audio query.m4a          # full grounded recommendation
python run_query.py --mic 8                    # record 8 seconds, then ask
python Semantic_Analysis/03_search.py --audio spec.wav --top-k 3
python Semantic_Analysis/03_search.py --mic 8 --lang hi
```

The transcript is **always printed before the results**. Speech recognition is
the least reliable link in this chain and the only one you can sanity-check at a
glance, so hiding it would hide the thing most likely to be wrong:

```
HEARD:
  transcript : IS-1786 TMT reinforcement bars, Fay 500 D-grade, 25 mm diameter
  normalised : IS 1786 TMT reinforcement bars, Fe500D grade 25 mm diameter
  rewrote    : 1786 -> 1786, Fay 500 D-grade, -> Fe500D, 25 -> 25
  language   : English (eng_Latn) by langdetect; Whisper heard en 1.00
  audio      : 10.7s
```

---

## What is supported

| | |
|---|---|
| Model | `faster-whisper` `small`, int8, CPU. ~484 MB, downloaded once, offline after that |
| Audio files | `.wav`, `.mp3`, `.m4a` claimed and accepted; `.flac`, `.ogg`, `.webm` also pass through the decoder |
| Microphone | `--mic SECONDS`, 16 kHz mono, capped at 120 s (`IS_ADVISOR_MIC_MAX_SECONDS`) |
| Languages | whatever Whisper transcribes, then reconciled against our own detector; the 22 scheduled languages plus English are first class downstream (`multilingual/README.md`) |
| Notation normaliser | **Hindi and English** number words, letter names, units and grade/citation prefixes |
| Cost | free, no API key, nothing uploaded |

### How the language is decided

Whisper reports the language it thinks it heard. That is reliable about the
*speech* and unreliable about the *script*, and the script is what everything
downstream needs: the translator needs the code whose script the text is
actually in. So the order of authority is:

1. **`--lang`** — a caller who names the language knows something neither the
   audio nor the transcript can tell us.
2. **The script of the transcript**, via `multilingual.detect`. Whisper saying
   `hi` over Urdu-script text does not make that text Devanagari.
3. **Whisper's guess**, as the tie-breaker for Latin-script text, where the
   script says nothing on its own and our function-word tables are weakest.

The three ways Hindi comes back, and what each does:

| Whisper returns | Handled as | Then what |
|---|---|---|
| Devanagari | `hin_Deva` | translated to English by NLLB, answer localised back to Hindi |
| Urdu script | `urd_Arab`, with the mismatch reported | translated as Urdu, which NLLB carries. The *speaker* said Hindi; the text is Urdu script, and translating the script in front of us is the honest reading |
| Romanised ("TMT sariya chahiye") | `hin_Deva` with `romanised=True` | **not** machine-translated, by design — the curated trade names already match it (`multilingual/README.md`) |

A disagreement between Whisper and the script is never hidden; it is printed as
`note:` in the HEARD block and carried on the transcript as `language_mismatch`.

### What the notation normaliser does

Tested cases, all in `tests/test_speech_notation.py`:

| Spoken | Becomes |
|---|---|
| `आई एस सत्रह सौ छियासी` | `IS 1786` |
| `आई एस एक हज़ार सात सौ छियासी` | `IS 1786` |
| `एफ ई पाँच सौ डी` | `Fe500D` |
| `पच्चीस मिलीमीटर` | `25 mm` |
| `eye ess seventeen eighty six` | `IS 1786` |
| `eye ess one seven eight six` | `IS 1786` |
| `twenty five millimetre` | `25 mm` |
| `dee en one hundred fifty` | `DN 150` |
| `IS-1786` (a Whisper artefact) | `IS 1786` |
| `IP 66`, `SS 304` | `IP66`, `SS304` |

Three judgement calls worth knowing, because each was a bug first:

- **`IS-1786` matters more than it looks.** Whisper writes the hyphen, and
  `is_advisor.query.IS_NUMBER_RE` accepts a colon or a dot between the prefix
  and the digits but **not a hyphen** — so the citation was silently lost and
  the standard never got pinned. Nothing in the output said why.
- **English letter names are restricted.** Read literally, "I see you are here"
  is I-C-U-R. An ambiguous English name (`see`, `are`, `you`, `why`, `eye`,
  `oh`, `tea`) only counts as a letter when a number follows it or the run
  spells a prefix the dataset uses. Devanagari letter names have no such
  collision, so they are accepted unconditionally.
- **Material abbreviations are not glued to numbers.** `GI 25 mm pipe` is
  galvanised iron pipe of 25 mm; gluing it into `GI25 mm` would invent a grade
  and strip the size of its number. Only grade and rating prefixes glue, and
  only when the digits are not a measurement.

Anything it does not recognise it leaves exactly as it was. That is the safe
direction: an unconverted `सत्रह सौ` retrieves badly, a wrongly converted one
retrieves the wrong standard confidently.

---

## What is not supported, and what is not claimed

**No measured accuracy, in any language.** This is the important one. What has
been verified is that the path works end to end: audio in, the right standard
out. The two clips used for that were generated with Windows SAPI
text-to-speech, because no recording of real speech was available — synthetic
English TTS is clean, unaccented and unhesitant, so it says **nothing** about
how this behaves on real Indian-accented Hindi or English in a noisy office. No
word error rate has been measured. Treat the transcript as a draft you read
before trusting, which is why it is printed.

What the two clips did establish, verbatim:

| Spoken (SAPI) | Whisper returned | After normalisation |
|---|---|---|
| "eye ess seventeen eighty six. T M T reinforcement bars, Fe five hundred D grade, twenty five millimetre diameter." | `IS-1786 TMT reinforcement bars, Fay 500 D-grade, 25 mm diameter` | `IS 1786 TMT reinforcement bars, Fe500D grade 25 mm diameter` |
| "L E D street light, ninety watts, I P sixty six protection." | `LED streetlight, 90 watts, IP66 protection` | `LED streetlight, 90 W, IP66 protection` |

Both then retrieved the correct standard at rank 1 — `IS 1786:2008` pinned as a
citation, and `IS 16107 (Part 2/Sec 2):2017` for the luminaire. Note that
Whisper heard "Fe" as "Fay": the `Fe500D` recovery comes from a table entry
whose provenance is that transcript, not from the model getting it right.

**Voice-activity detection is off.** `onnxruntime` — a faster-whisper
dependency, used only for VAD — **segfaults on import** on this machine
(Windows, Python 3.11, Ryzen 5 5500U): no exception, exit code 139.
Transcription does not touch it, so the only cost is that silence is transcribed
as nothing rather than being trimmed first. `IS_ADVISOR_WHISPER_VAD=1` turns it
on where onnxruntime behaves.

**Two pins are load-bearing**, both found by things crashing:
`ctranslate2==4.6.0` (4.8.2 segfaults on model construction; 4.7.0 looks for a
ROCm path Windows wheels do not ship) and `setuptools<81` (ctranslate2 4.6.0
imports `pkg_resources`, which setuptools removed in 81). `requirements.txt`
carries the reasoning.

Also not supported:

- **Notation normalisation in languages other than Hindi and English.** A Tamil
  or Bengali dictated IS number is transcribed and passed through unchanged; the
  number words and letter names are not converted. The tables are the work, not
  the mechanism, so adding a language is data entry in `notation.py`.
- **Hindi cardinals only to 99** plus `सौ` / `हज़ार` / `लाख`. Beyond that the
  words pass through as words.
- **No line-item splitting of dictated tenders.** A dictated paragraph listing
  six products is one query, exactly as a typed one would be — the splitter
  reads punctuation, and dictation has little.
- **`--mic` records for a fixed window.** It does not stop when you stop
  talking, and it needs `sounddevice` (`--audio FILE` does not).
- **No speaker diarisation, no streaming, no real-time partial results.**
- **Model size is not tuned.** `small` was chosen because it is the largest that
  answers in seconds on a CPU laptop, not because it was compared against `base`
  or `medium` on this domain. `IS_ADVISOR_WHISPER_MODEL` changes it.

## Timings

On this machine (Ryzen 5 5500U, CPU, int8), wall clock including model load on
the first call: **25.9 s** for 10.7 s of audio, then **10.7 s** for 6.1 s of
audio once the model was warm. Machine-dependent, and a single observation
each — read them as an order of magnitude, not a benchmark.
