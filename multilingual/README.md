# Multilingual input and output

Ask in any of the 22 scheduled Indian languages, get the answer back in that
language. This package is shared by both workstreams — `Semantic_Analysis/`
(retrieval) and `rag/` (grounded recommendation) — and it sits at the **edges**
of both, not inside them.

```
query in any language
  ↓  detect.py        script decides, marker words break the ties
  ↓  detect.normalise NFC, and Indic digits folded to ASCII
  ↓  protect.lift     IS numbers and grade codes taken out of harm's way
  ↓  translate.py     IndicTrans2 (gated) or NLLB-200, locally, on CPU
  ↓  glossary.py      native trade terms → the English terms the index holds
  ══════════════════  the existing English pipeline, unchanged
  ↓  localize.py      the answer translated back; identifiers left alone
answer in the language it was asked in
```

Two invariants hold everywhere, and both exist to protect correctness that was
established in English:

1. **Retrieval, the knowledge graph, the LLM and the grounding validator only
   ever see English.** Localisation is the last step. `rag/grounding_validator.py`
   rejects claims by matching IS numbers and clause patterns in the model's
   prose; translating before it ran would mean validating nothing.
2. **Identifiers are never translated.** `IS 1786` stays `IS 1786`. Official
   titles stay English — a procurement officer has to quote the English title in
   a tender — and get a machine-translated gloss *beside* them in
   `title_localized`.

Nothing here needs an API key, and nothing touches the network after the first
model download.

---

## What the project could do before, and what changed

The starting point was narrower than "Hindi and English". Measured, not assumed:

| Input | Before | Now |
|---|---|---|
| English | full pipeline | unchanged |
| Romanised Hindi ("TMT sariya Fe500D") | worked, via 57 curated trade names in `Semantic_Analysis/data/aliases.csv` | detected as Hindi, still searched as typed, answered in Devanagari |
| Devanagari ("टीएमटी सरिया") | **failed** | translated, searched, answered in Hindi |
| Tamil, Bengali, Telugu, Urdu, … | **failed** | translated, searched, answered in that language |

The Devanagari case failed for a reason worth recording, because it was the
larger of the two blockers: `Semantic_Analysis/is_advisor/lexical.py` tokenised
on `[a-z0-9]+`, so `'आरसीसी कार्य के लिये टीएमटी सरिया 500डी'` tokenised to
exactly `['500']`, and Tamil tokenised to `[]`. BM25 is the **stronger** of the
two retrievers on this corpus (Recall@5 0.909 keyword-only against 0.826 dense,
README section 7), so an Indic query was reaching the weaker half of the system
at best. Fixing only the embedding would have left that in place.

Four things had to change, not one:

1. **The keyword tokenizer** now keeps letters, digits and Indic combining
   marks. 65 of 23,341 indexed documents tokenise differently as a result
   (0.28%, all non-ASCII characters deep inside a title).
2. **The bi-encoder** is `intfloat/multilingual-e5-small` instead of
   `BAAI/bge-small-en-v1.5` — same 384 dimensions, so the index keeps its shape
   and disk cost, and ~100 languages instead of one.
3. **The query layer** splits the document as typed and translates each line
   item, because everything after splitting (boilerplate patterns, citation
   regex, gazetteers, spaCy) is English-specific.
4. **The output layer** exists at all, because the corpus cannot supply it:
   33,803 of 35,524 standards are marked English, 120 bilingual, 17 Hindi. A
   same-language answer is *produced*, never looked up.

---

## Modules

| File | Responsibility |
|---|---|
| `languages.py` | The registry. 22 scheduled languages + English as `first_class`, 14 others as `best_effort`. FLORES-200 codes (`hin_Deva`), which both MT engines use, plus ISO aliases so a caller can send `"hi"`. |
| `detect.py` | Script-first detection, marker words for the four shared scripts, romanised-Indic detection, Indic digit folding. Reports *how* it decided. |
| `protect.py` | Keeps `IS 1786`, `Fe500D`, `IP66`, `DN 150` intact across a translation. Two strategies, one per direction — see below. |
| `translate.py` | IndicTrans2 and NLLB-200 backends, lazy-loaded, batched, cached, and degrading to "returned the original, here is why" rather than failing. |
| `glossary.py` | Native-script trade terms → the English trade terms the keyword index actually contains. The same idea as `aliases.csv`, one step further out. |
| `localize.py` | The output side. Curated labels where they exist, MT for free text, identifiers never touched. |
| `config.py` | Model ids, generation settings, cache size, every one an env override. |
| `data/glossary.csv` | 76 seed rows across seven languages. A seed, not a vocabulary — see *Limits*. |

---

## Detection: why script rules and not a language model

The script is decisive for every Indian language **except** the ones that share
a script. Tamil text can only be Tamil; Gujarati can only be Gujarati. A
statistical identifier adds nothing there but a way to be wrong. So Unicode
ranges decide those, and marker words — function words and copulas only — break
only the ties the script genuinely leaves open:

| Script | Languages that share it | How the tie breaks |
|---|---|---|
| Devanagari | Hindi, Marathi, Nepali, Sanskrit, Maithili, Konkani, Bodo, Dogri | marker words; Hindi on no evidence, as the overwhelming prior for procurement text |
| Bengali | Bengali, Assamese, Manipuri | the two Assamese-only letters `ৰ` `ৱ` first, then marker words |
| Arabic | Urdu, Kashmiri, Sindhi (+ Persian, Arabic) | Sindhi-only and Kashmiri-only letters, then marker words, Urdu by default |
| Latin | English, romanised Indic, other Latin-script | romanised markers, then `langdetect` if installed, then function-word tables |

An Indic script needs only a **10% share** of the letters to decide, not a
majority: an Indic query routinely carries English fragments (`IS 1786`,
`Fe500D`, `IP66`), and the reverse — a Devanagari fragment inside an English
tender — is rare, where mis-routing costs only a needless translation of text
that was already English.

A **declared** language always wins (`--lang hi`, `{"language": "hi"}`), because
a caller who names it knows something the text cannot say, and because being
wrong about the *output* language is more annoying than being wrong about the
input.

### Romanised input is detected and deliberately not translated

"TMT sariya Fe500D chahiye" comes back as `hin_Deva` with `romanised=True`, and
is then searched **as typed**. That is not a gap. Those exact trade names are
what `aliases.csv` holds and what BM25 matches as tokens, and that path is
measured (README section 7 puts the curated trade names at +0.115 Recall@5).
Feeding it to a model trained on Devanagari would trade a measured path for an
unmeasured one. The answer still comes back in Devanagari, since that is the
language that was detected.

---

## Protection: two strategies, because the directions differ

A procurement query is mostly notation, and the notation decides the answer. An
`IS 1786` that returns as `IS 1,786` stops matching the citation regex in
`is_advisor/query.py`; a `Fe500D` that returns as `Fe500 D` stops matching the
index.

**Into English** (`lift` / `reattach`) — the spans are pulled out, the prose is
translated without them, and they are appended to the result. The query is a bag
of terms by the time BM25 and the bi-encoder see it, so position does not matter,
and nothing can come back mangled because nothing was ever handed to the model.

**Out of English** (`mask` / `unmask`) — placeholders, because a human reads this
text and word order matters. The placeholder shape is `@1@`, `@2@`, and it was
**measured rather than reasoned about** — see *The placeholder shape* below.
`unmask` matches tolerantly (the model may space it out, or render the digit in
the target script's numerals) and **reports what it could not place**, which the
caller appends in brackets — a recommendation that silently drops its IS number
is worse than one that reads awkwardly.

One asymmetry worth knowing: **numbers stay inline going into English**. Lifting
a number separates it from its unit, and `is_advisor/requirements.py` reads a
number *adjacent to* its unit, so `500 लिटर` has to stay together to be
extracted as a capacity. Digits are folded to ASCII first, and models keep ASCII
digits far more reliably than they keep an invented placeholder.

---

## Translation engines, and the gate in front of the better one

| Engine | Covers | State |
|---|---|---|
| `ai4bharat/indictrans2-*-dist-200M` | the 22 scheduled languages, including Bodo, Dogri, Konkani and Santali, the four the installed NLLB-200 does not carry | wired and preferred — **gated on HuggingFace** |
| `facebook/nllb-200-distilled-600M` | ~200 languages, including most of the scheduled ones | the working default, ungated, ~2.5 GB |

**IndicTrans2 is gated** (`gated=auto` on both checkpoints, confirmed against the
HuggingFace API). Using it needs a HuggingFace account, the model terms
accepted, and `HF_TOKEN` in the environment. Without a token the layer loads
NLLB instead, and `GET /health` reports which backends actually came up —
"which MT model is really answering" is exactly the kind of thing that silently
differs between machines.

`IndicTransToolkit`, IndicTrans2's official preprocessor, needs a C compiler and
does not build on a stock Windows install. `translate.py` falls back to
prepending the language tags itself, which is the part the model requires; what
is lost is cross-variant script normalisation, and `detect.normalise` already
does the NFC half of that.

**Batching is what makes this affordable on CPU.** A tender is many short lines
and an answer is a dozen short strings, so `to_english_batch` translates every
line item in one model call and `Localizer.prime` translates every string in a
response in one more. Everything is cached by `(text, source, target)`, and the
masking is deterministic, so a primed string is a cache hit when the per-field
call formats it.

---

## Output: three kinds of text, handled differently

| Kind | Treatment | Example |
|---|---|---|
| Identifiers | never translated | `IS 16107 (Part 2/Sec 2):2017` |
| Official titles | kept, with a gloss beside them | `title` stays English, `title_localized` is the gloss |
| Text the pipeline wrote | translated | `why`, `reason`, `warnings`, tier names, citation notes |

Labels and enum values (`Highly relevant`, `withdrawn`, `product`) go through a
**curated table** where one exists and the model otherwise, because two words out
of context is where MT is weakest and where a wrong word is most visible. Hindi
is curated; every other language falls back to the model, and every localised
string says which happened (`curated`, `mt`, `untranslated`, `original`).

Localised fields are **additive**: `*_localized` keys appear only for a
non-English query, and the English keys keep their meaning in every case, so an
existing consumer of the JSON contract reads exactly what it read before.

---

## Using it

```bash
# retrieval only (Semantic_Analysis)
python Semantic_Analysis/03_search.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D"
python Semantic_Analysis/03_search.py --file tender_hi.txt --lang hi
python Semantic_Analysis/03_search.py "GI pipes 25mm" --lang ta    # English in, Tamil out
python Semantic_Analysis/03_search.py "GI pipes 25mm" --no-translate

# full grounded recommendation (rag)
python run_query.py "90W LED street light IP66" --lang hi
```

```python
from multilingual import prepare_query

detection, translation, english = prepare_query("आरसीसी कार्य के लिये टीएमटी सरिया")
detection.code        # 'hin_Deva'
detection.method      # 'script+markers'
english               # 'TMT bar for RCC work ... TMT bar reinforcement steel'
```

```
POST /recommend   {"query": "...", "language": "hi"}    # language optional
GET  /languages                                        # what is supported, and how well
GET  /health                                           # which MT backends actually loaded
```

Environment switches, all optional: `IS_ADVISOR_TRANSLATE=0` disables
translation entirely (detection and glossary still run),
`IS_ADVISOR_TRANSLATE_TITLES=0` drops the title glosses,
`IS_ADVISOR_MT_BEAMS` raises decoding quality at roughly one second per beam per
line item, `IS_ADVISOR_NLLB_MODEL` swaps the checkpoint.

---

## What the translations actually look like

Run against `facebook/nllb-200-distilled-600M` on CPU, with the notation protection and the glossary
in place. These are verbatim, not illustrative, and they are here so the quality can be judged rather
than asserted.

**Into English** (the retrieval direction). The bracketed timing is wall clock on a CPU that was busy
with an index build; the first row includes the 2.5 GB checkpoint load.

| In | Out |
|---|---|
| `आरसीसी कार्य के लिये टीएमटी सरिया Fe500D चाहिये, IS 1786 के अनुसार` | `TMT Saria is required for RCC work, according to Fe500D IS 1786 bar reinforcement steel` (16.4 s, including the checkpoint load) |
| `बाहर लगाने के लिये 500 लिटर की स्टेनलेस स्टील पानी की टंकी` | `500 litre stainless steel water tank for discharge storage` (2.6 s) |
| `पाणी साठवणुकीसाठी स्टेनलेस स्टील टाकी आहे आणि 500 लिटर क्षमता` (Marathi) | `It has a stainless steel tank for water storage and a capacity of 500 litres.` (3.3 s) |
| `நீர் விநியோகத்திற்கு 25 மிமீ கால்வனைஸ் இரும்பு குழாய் தேவை` (Tamil) | `25 mm galvanized iron pipe is needed for water supply` (2.3 s) |
| `সড়ক বাতির জন্য 90W LED লুমিনেয়ার প্রয়োজন, IP66` (Bengali) | `LED luminaires are needed for street lighting 90W IP66` (2.2 s) |

Every `IS 1786`, `Fe500D`, `IP66`, `90W` and `25 mm` came through intact, which is what `protect.py`
is for. The first row also shows the glossary earning its place: NLLB transliterated सरिया as "Saria"
rather than translating it, and `bar reinforcement steel` was appended from `data/glossary.csv`, which
is the wording the keyword index actually contains.

**Out of English** (the presentation direction).

| In | Out (Hindi) |
|---|---|
| `IS 1786:2008 covers high strength deformed steel bars for concrete reinforcement.` | `IS 1786:2008 कंक्रीट कंक्रीट कंक्रीट के लिए उच्च शक्ति विकृत स्टील बारों को कवर करता है।` |
| `The cited standard IS 2062 is withdrawn; it was replaced by IS 2062 (Part 1):2025.` | `उद्धृत मानक IS 2062 को वापस ले लिया गया है; इसे IS 2062 (Part 1):2025 द्वारा प्रतिस्थापित किया गया है।` |
| `matched led, street; semantically similar title; product specification` | `समरूपता वाला एलईडी, सड़क; अर्थिक रूप से समान शीर्षक; उत्पाद विनिर्देश` |
| `cited standard is current; the edition shown is the latest` | `उद्धृत मानक वर्तमान है; दिखाए गए संस्करण नवीनतम है` |

Every IS number, part number and year is in place, which is the property that
matters. The first row also shows what this layer does *not* fix: `कंक्रीट कंक्रीट
कंक्रीट` is NLLB repeating itself, a degenerate-decoding artefact of a 600M
distilled model under greedy decoding. Raising `IS_ADVISOR_MT_BEAMS` reduces it
at about a second per beam per string. It is a translation-quality limit, not a
correctness one, and it is why the English text is always kept alongside.

### The placeholder shape, and how it was chosen

The first version used letter-only placeholders (`PLHA`, `PLHB`), on the theory
that digits are what a translation model reformats between locales. Running it
showed the opposite problem:

```
en : IS 1786:2008 covers high strength deformed steel bars for concrete reinforcement.
hi : पीएलएचए उच्च शक्ति के कंक्रीट कढ़ाई के लिए विकृत स्टील बारों को कवर करता है। (IS 1786:2008)
```

`पीएलएचए` is `PLHA` **transliterated into Devanagari**; Tamil produced
`பிஎல்ஹே`. A model does that to anything that looks like a name, and tolerant
matching cannot find it, so the IS number fell out of the sentence and only the
bracketed fallback saved it.

Leaving the notation inline instead does not work either, and that is worth
knowing before anyone tries it: NLLB renders `IS 1786:2008` as
`आईएस 1786:2008` in Hindi — it transliterates the `IS` — in the middle of a
sentence as readily as at the start. Masking is genuinely necessary here.

So nine candidate shapes went through the real model in Hindi and Tamil. The
result was clean: punctuation-delimited numerals survive, letter forms do not.

| Shape | Hindi | Tamil |
|---|---|---|
| `PLHA` | ✗ transliterated | ✗ transliterated |
| `X1X` | ✗ transliterated | ✓ |
| `#1`, `\|1\|` | ✗ split or dropped | ✗ split or dropped |
| `[1]`, `<1>`, `{1}`, `(1)`, `@1@` | ✓ | ✓ |

`@1@` is the pick. `[1]` survives just as well but is exactly the evidence-tag
notation `rag/context_builder.py` already uses, so a placeholder in that shape
could collide with real content in an LLM's `reason` text. The digit inside can
still be re-rendered in the target script's numerals, so `unmask` matches every
Unicode spelling of it.

A **verified second attempt** stays as the second line of defence. If a
placeholder still does not come back, the sentence is translated again with the
real notation inline, and whichever attempt keeps more of the notation wins — a
value only counts as kept if it appears **verbatim**, so the reformatting that
masking exists to prevent is checked for rather than assumed away. The retry is
batched and cached, so it costs one extra model call for the sentences that need
it and nothing for the ones that do not. With `@1@` it now rarely fires; with
`PLHA` it fired on every sentence that opened with a citation.

## Limits

- **The glossary is a seed, not a vocabulary.** 76 rows across seven languages,
  written only where the native term was confidently known. Growing it from real
  multilingual tender lines is the honest path, the same argument
  `Semantic_Analysis/README.md` section 4 makes about mined gazetteers versus
  hand-written ones.
- **Romanised Marathi and Bengali resolve poorly.** Telling romanised Hindi from
  romanised Marathi by marker words is unreliable; both return Hindi-family with
  a low confidence, and the flag says the verdict came from markers.
- **Two query rules go quiet on caseless scripts.** `rejoin_wrapped_lines` needs
  a lowercase continuation and `is_heading` needs an all-caps line, so a wrapped
  Devanagari paragraph stays several line items and a Devanagari heading is
  searched rather than dropped. Both fail *quietly* rather than firing wrongly,
  which is the safer direction.
- **A non-English `Key: value` block loses the key-names-the-field shortcut.**
  The keys are detected (the pattern accepts Indic and Arabic script) and shown,
  but they are not English keys, so the fields come from text extraction
  instead of from the labels.
- **Translation quality is not measured here.** The retrieval numbers in
  `Semantic_Analysis/README.md` section 7 are English-input numbers, and they
  are still the only measured ones. A multilingual evaluation set — the same 121
  line items, translated and checked by a speaker — is the missing piece, and it
  is recorded as the top item in `NEXT.md`.
- **Language detection is per document, not per line item.** A three-word line
  carries almost no language signal; the tender it came from carries plenty. A
  genuinely mixed-language tender gets one language for all of its items unless
  `--lang` says otherwise.
