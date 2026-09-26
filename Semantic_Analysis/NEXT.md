# NEXT — what was built, and what is still open

`README.md` documents the workstream as it stands. This file records how the five planned items
turned out, so the next person does not rebuild something that was already measured and dropped.

Read `README.md` first, especially section 7 (measured results), section 8 (why the evaluation
numbers are an upper bound) and section 13 (known limits).

**Constraints that did not change.** Fully offline, no LLM API calls, no network after the first
model download. Metadata is a boost, never a filter.

---

## Status

| Feature | State |
|---|---|
| 1A Product description | done |
| 1B Technical specification (`Key: value` block) | done — item 1 |
| 1C Tender PDF upload | done — item 4 |
| 2 Requirement extraction | done — item 2 |
| 3 Semantic standard search | done, measured, ablated |
| 4 Ranking | done — fusion, boosts, 0–1 score, relevance tiers (item 3) |
| Requirement-match ranking signal | **built, measured, removed** — item 5 |
| Multilingual input and output | done — item 6, README section 14 |

Items 1 to 4 do not touch retrieval, and the headline numbers confirm it: the shipping configuration
still measures Recall@5 = 0.883 and Recall@10 = 0.942, unchanged.

---

## Item 1 — `Key: value` specification blocks (done)

Two or more consecutive `Key: value` lines are detected as one specification block before line
splitting runs, and collapse into a single line item. Without this, a five-attribute block became
five searches, and "Material: Stainless steel" on its own returned stainless steel standards
unrelated to the product.

- The product name comes from a title line immediately above the block, or from a
  `Product`/`Item`/`Description` key.
- Commercial keys (`Warranty`, `Quantity`, `Delivery`, `Rate`, …) are kept in the parsed pairs for
  display but left out of the query text.
- The parsed pairs pass to requirement extraction as pre-labelled fields, where the key names the
  field and nothing has to be inferred.

The heading rule composes correctly with this, as the spec asked: `Capacity: 200 L` has a value so
it is an attribute, while a bare `Technical Specification:` has none and is still dropped as a
heading. Both cases are covered by tests.

---

## Item 2 — Requirement extraction (done)

`is_advisor/requirements.py` emits the labelled object: `product`, `material`, `quantities`,
`environment`, `properties`, `unmapped`. The specification's worked example passes field for field,
including that the order count of 100 is not captured as a capacity.

Quantities handle qualifiers ("minimum", "not less than", "up to"), ranges collapsed into one entry
with an upper bound, unit-first notation (`DN 150`), Indian digit grouping (`1,00,000`), and a
dimension check so that "32 mm diameter, quantity 45 MT" does not report the tonnage as a diameter.

**Gazetteers are mined, not hand-written**, by `05_mine_gazetteers.py` from `title_clean` across the
indexed corpus: 139 material terms, 35 property, 18 environment. A documented review list removes
candidates that read like properties but are measured laboratory quantities. A hand-maintained
`*_manual.txt` sits beside each generated file, merged at load time and never overwritten, adding 25
material, 22 property and 20 environment terms for procurement shorthand such as "GI", "SS 304" and
"FRLS" that BIS titles never spell that way.

### Where the specification's estimates differed from measurement

The spec quoted attribute coverage over indexed titles. Measured against the mined gazetteers, two
of the four differ materially:

| Attribute vocabulary | Spec estimate | Measured |
|---|---|---|
| material | 8.9% | **15.6%** |
| property | 5.8% | **2.1%** |
| environment | 3.1% | 2.4% |
| numeric specification | 1.4% | 1.6% |

The conclusion the spec drew from these numbers is unchanged and was confirmed by item 5: coverage
is far too low for a requirement-match ranking signal, and no requirement field is used as a filter.

---

## Item 3 — Relevance tiers (done)

The existing 0–1 score is banded into `Highly relevant`, `Related` and `Possibly relevant`, with
thresholds fitted by `06_calibrate_tiers.py` rather than guessed. They have since been re-fitted
once, after item 6 changed the bi-encoder: **0.96 and 0.84 became 0.95 and 0.68**, because a new
encoder produces a new score distribution and a threshold fitted to the old one stops meaning what it
was fitted to mean. On the current index, 72.9% of gold answers land in the top tier, 22.0% in the
middle and 5.1% in the lowest, with 4.6% of non-gold candidates reaching the top tier - an upper
bound on false positives rather than a measurement of them.

Cited standards and pinned successor parts are always top tier regardless of the thresholds.

One trap worth recording: adding a new boost to the score ceiling depresses every score and silently
invalidates fitted thresholds. The ceiling now counts only boosts that are actually active, and the
calibration was re-confirmed after item 5 was removed. **Changing the encoder does the same thing for
the same reason**, and re-running `06_calibrate_tiers.py --apply` is therefore part of that change
rather than an optional follow-up.

---

## Item 4 — PDF input (done)

`03_search.py --file x.pdf` extracts text with `pdfplumber`, page by page, pulling table rows out
separately and joining cells with pipes so the existing row rules apply. `.txt` behaviour is
unchanged.

A PDF yielding fewer than 40 characters per page is reported as a scan rather than searched as an
empty string. Optical character recognition remains out of scope.

Fixtures live in `tests/fixtures/` and are generated by `tests/make_fixtures.py`, which assembles
the PDFs byte by byte so the test suite needs no PDF-writing dependency.

---

## Item 5 — Requirement-match boost (built, measured, removed)

A 0.04 boost when an extracted material or property term appeared in a candidate's indexed text,
measured against `data/eval_set.jsonl` with the rest of the pipeline held fixed:

| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| hybrid (shipping default) | 0.725 | 0.883 | 0.942 | 0.794 |
| hybrid + requirement boost | 0.717 | 0.883 | 0.942 | 0.784 |

Recall@5 and Recall@10 are identical; Recall@1 and MRR are slightly worse. The specification said to
delete it in that case, so the code is gone rather than kept as an unmeasured feature. The coverage
table above explains it: 85% of indexed titles name no material at all, so for most candidates the
boost has nothing to fire on, and where it fires it mostly rewards standards already ranked highly.

Requirements are still extracted, displayed and returned in the output. They just do not move the
ranking, and the README says so.

---

## Item 6 — Multilingual input and output (done)

Any of the 22 scheduled Indian languages in, the same language out. The layer lives in the repo-root
`multilingual/` package, shared with the RAG workstream, and has its own README. README section 14
is what it means for retrieval.

Four things had to change, and the one that mattered most was not the embedding model:

1. **The keyword tokenizer.** `[a-z0-9]+` discarded every non-Latin character, so
   `'आरसीसी कार्य के लिये टीएमटी सरिया 500डी'` tokenised to `['500']` and `'கம்பி'` to `[]`. BM25 is
   the stronger retriever on this corpus, so an Indic query was reaching the weaker half of the
   system at best. 65 of 23,341 documents tokenise differently now (0.28%), which is why section 7
   was re-measured rather than assumed.
2. **The bi-encoder**, `BAAI/bge-small-en-v1.5` → `intfloat/multilingual-e5-small`. Same 384
   dimensions, so the index kept its shape and its 35 MB. Two traps came with it: e5 needs a
   *document* prefix as well as a query prefix, and the old prefix logic sniffed the model name
   (`"bge" in ...`) so it would have silently applied none; and the stale-vector guard compared only
   the text fingerprint, which cannot see an encoder swap - the text does not change, and the vectors
   are left the right shape with the wrong meaning. `index_meta.json` now records the model and the
   guard compares it.
3. **The query layer.** Splitting runs on the text as typed, because it reads punctuation;
   everything after splitting runs on an English translation, because everything after splitting is
   English-specific.
4. **An output layer**, because the corpus cannot supply one: 33,803 of 35,524 standards are marked
   English. A same-language answer is produced, not looked up. IS numbers and official titles are
   never translated - a tender has to quote the English title - and a gloss is offered beside them.

### Two decisions worth not relitigating

**Romanised input is not machine-translated.** "TMT sariya Fe500D chahiye" already retrieves through
the curated trade names in `data/aliases.csv`, which section 7 measures at +0.115 Recall@5. Sending
it to a model trained on Devanagari would trade a measured path for an unmeasured one. It is detected
as Hindi, searched as typed, and answered in Devanagari.

**Localisation runs last, after the RAG grounding validator.** The validator matches IS numbers and
clause patterns in the model's prose, so translating first would mean validating nothing while
appearing to validate everything.

### What is not done

**IndicTrans2 is gated.** Both checkpoints are `gated=auto` on HuggingFace (confirmed against their
API), so they need an account, the terms accepted, and `HF_TOKEN`. They stay wired and preferred -
they are the better models for these languages, and the only ones carrying Bodo, Dogri, Santali and
Manipuri - but the shipping default is `facebook/nllb-200-distilled-600M`. `GET /health` reports
which backend actually loaded.

**No measured retrieval quality in any language but English.** See the first item below.

---

## Still open, and still the highest value

Both were already named in README section 13 and nothing built here substitutes for either.

1. **A multilingual evaluation set.** `data/eval_set.jsonl` is English, so every number in this
   workstream measures English input. Translating those 121 items and having a speaker check them
   would measure the multilingual path end to end for the first time - today the retrieval side is
   measured and the translation in front of it is not.
2. **Replace the hand-written evaluation set with real tender lines.** Every number in this
   workstream is an upper bound until this is done, and the same corpus is the strongest vocabulary
   source available. Real *multilingual* tender lines would also be the honest way to grow
   `../multilingual/data/glossary.csv`, which is a 76-row seed written where the native term was
   confidently known.
3. **Scope-text extraction from the standard PDFs.** Clause 1 is the missing input behind the
   requirement-match result above, behind the multi-part misses in README section 7, and behind the
   absence of any scope-match component. `pdfplumber` is now already a dependency, so the path is
   open.

Smaller, genuinely untried:

- **Field weighting in the keyword index.** Title, classification path, mined vocabulary and aliases
  are concatenated into one string, so a long alias list lengthens the document and BM25 penalises
  it. README section 7 shows this costing a retrieval that the alias was added to help.
- **A reranker suited to short documents.** The current cross-encoder is a general passage ranker
  and measures as a loss; that is a verdict on this model, not on reranking.
- **Under-splitting of run-on prose.** The rules handle bullets, numbering, table rows and
  specification blocks. One paragraph hiding three products is still one line item.
- **Transliteration for romanised input.** Romanised Indic is searched as typed today. Transliterating
  it to native script would let the translation path see it too, and would separate romanised Marathi
  from romanised Hindi, which marker words cannot do reliably.
- **Curated labels beyond Hindi.** Tier names and statuses are hand-translated for Hindi and
  machine-translated elsewhere. Two words out of context is where MT is weakest; a speaker of each
  language reviewing about twenty strings would fix it permanently.
