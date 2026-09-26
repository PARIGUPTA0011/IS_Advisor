# Semantic Analysis — procurement spec to candidate Indian Standards

Takes a procurement specification, splits it into line items, and returns a ranked list of candidate
Indian Standards for each one. That ranked list is where this workstream ends.

It accepts three shapes of input: a free-text product description, a labelled `Key: value`
specification block, or a tender file as text or PDF. For each line item it reports the requirements
it understood, then ranked candidate standards in three relevance tiers, with any standard the
tender cited resolved even when that standard has been withdrawn.

The specification may be written in any of the 22 scheduled Indian languages, and the answer comes
back in the language it was asked in. Section 14 covers how, and `../multilingual/README.md` is the
reference for the layer itself.

Everything runs locally on CPU. No API key is used anywhere in the pipeline, and after the first
model download nothing needs the network.

`NEXT.md` is the companion to this file: it records how each planned feature turned out, including
the one that was built, measured and deleted, and what is still open.

---

## 1. Quick start

```bash
pip install -r ../requirements.txt
python -m spacy download en_core_web_sm          # optional, improves phrase extraction

python 01_build_index.py                         # 8-25 min on CPU, embeddings dominate
python 01_build_index.py --no-dense              # ~8 s, corpus + keyword index only
python 05_mine_gazetteers.py --report            # attribute vocabulary, ~5 s

python 03_search.py "TMT bars Fe500D for RCC work"
python 03_search.py --file data/sample_tender.txt --top-k 5
python 03_search.py --file tender.pdf                          # PDF input
python 03_search.py "GI pipes 25mm nominal bore" --json -      # JSON to stdout

python 03_search.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D"    # answered in Hindi
python 03_search.py --file data/sample_tender_hi.txt --lang hi # Hindi tender fixture
python 03_search.py "GI pipes 25mm" --lang ta                  # English in, Tamil out
python 03_search.py "GI pipes 25mm" --no-translate             # English-only path

python 02_evaluate.py --ablate --show-misses 10
python 04_ablate_vocabulary.py
python 06_calibrate_tiers.py                     # add --apply to write thresholds
python 02_evaluate.py --set tenders              # the real-tender evaluation set
python tests/test_pipeline.py

python ../demo/server.py                         # offline demo with the knowledge graph, see demo/README.md
```

Use `--no-dense` on the build while iterating on text cleaning; it skips the only slow step.

The first non-English query downloads a translation checkpoint (~2.5 GB, section 14). Nothing else
needs the network, and an install with no checkpoint still answers - in English, saying why.

### If the pinned versions will not import

The pins in `../requirements.txt` are not portable to every CPU machine. On Windows with an Anaconda
Python 3.11, `torch==2.14.0` fails at import with `OSError: [WinError 1114] ... c10.dll`, and
dropping to an older `torch` then breaks `transformers==5.17.0` with `NameError: name 'nn' is not
defined`. Both are import-time failures inside the dependency, not in this package. A verified
working combination on that machine:

```bash
pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu
pip install transformers==4.44.2 sentence-transformers==3.0.1 "huggingface-hub<0.26" "tokenizers<0.20"
pip install pdfplumber rank-bm25 faiss-cpu
```

Retrieval results are unaffected by this choice; only the embedding build time is, by roughly 3x
(section 6). Keyword-only work needs no more than `pdfplumber` and `rank-bm25`, which is the quickest
way to get `--no-dense` running without several hundred megabytes of `torch`.

`sentencepiece` belongs on the same list. It is what the translation tokenizers load their
vocabularies with, and **0.2.2 segfaults on import** under the Anaconda Python 3.11.7 above -
an immediate SIGSEGV, before any of this package runs. 0.1.99 imports and works on the same machine,
and `../requirements.txt` pins it there. Two other install facts worth knowing before debugging a
translation that never happens:

```bash
pip install "sentencepiece==0.1.99"     # 0.2.2 segfaults on import here
pip install langdetect                  # optional, Latin-script detection only
```

`IndicTransToolkit` (IndicTrans2's official preprocessor) needs a C compiler and does not build on a
stock Windows install; the translation layer falls back to prepending the language tags itself.

### Search flags

| Flag | Effect |
|---|---|
| `--file PATH` | read the specification from a `.txt` or `.pdf` file |
| `--json PATH` | write the JSON contract (`-` sends it to stdout) |
| `--top-k N` | candidates per line item, default 5 |
| `--rerank` | enable the cross-encoder, off by default (section 7) |
| `--no-dense` | keyword-only retrieval |

Text also arrives on stdin, so `cat tender.txt | python 03_search.py` works.

### Three shapes of input

A free-text product description, a labelled specification block, or a tender file:

```
Procure 100 stainless steel water storage tanks for outdoor
installation, minimum capacity 500 litres, resistant to corrosion
```
```
Product: Water storage tank
Capacity: 200 L
Material: Stainless steel
Installation: Outdoor
```

Both produce one line item. The block is detected before line splitting, because
splitting it by newline first would search "Material: Stainless steel" on its own and return
stainless steel standards that have nothing to do with the tank.

---

## 2. What gets indexed

**23,341 documents**: canonical, current, and the latest edition per `is_base_id`. All three
conditions matter, and the third is the one that is easy to miss. 540 base ids carry more than one
row marked `current`, so filtering on status alone leaves 1979 editions sitting next to 2026 ones.
The build takes the maximum `is_year` per base id, breaking ties on the higher `kys_id`.

A separate **lookup table holds all 35,524 rows including withdrawn standards**. Recommending and
resolving are different jobs: a withdrawn standard must never be recommended, but a tender that
cites one still needs it identified.

### Document text

Embedded text is title, plain-language title, aspect, the full classification path, and clause 1
scope text where a usable one exists:

```
Ordinary portland cement - Specification | Cement | Product Specification |
Building Materials including Paints Cement, concrete and Allied Products Cement and its Testing
```

The bare title is not enough. "Specification for Bund Former" carries no domain signal until the
classification path places it in agricultural implements.

**Scope text** comes from the free BSB Edge preview pages, collected by `bis_scope_scraper.py` into
`data/scope_text.csv` (method and coverage in `data/SCOPE_TEXT.md`). Only rows with status `ok` and
`title_overlap` of at least 0.35 are used, which is **11,280 standards, 48% of the index**. The
overlap gate drops the rows where bad OCR and mis-scraped pages concentrate. Adopted IS/ISO and
IS/IEC standards almost never have one, because their preview carries only the National Foreword.
That is a permanent limit of the source, not unfinished work.

Scope text goes into the embedding and deliberately **not** into the keyword string. Only some
documents have it, and appending it would roughly double their length, so BM25 length normalisation
would penalise exactly the documents it was added to help. It also has a separate keyword index of
its own. That index is built and measured, but it is off by default (section 7).

The keyword index sees three things the embedding does not:

- **Mined past-edition wording** — earlier editions of the same base id, withdrawn ones included,
  contribute words the current title dropped. 1,808 base ids gain vocabulary this way.
- **Curated trade names** — 57 rows in `data/aliases.csv` mapping procurement slang to standards:
  "TMT bar" and "sariya" to IS 1786, "DI pipe" to IS 8329, "aldrop" to IS 15834, "GI pipe" to
  IS 1239 Part 1. Trade names appear in no BIS text, so nothing else can supply them.
- **The IS number itself**, so that citing a number retrieves it.

These stay out of the embedded text deliberately. Pasting a dozen synonyms into a 20-word title
pulls the vector away from what the standard is actually about, while the keyword index treats each
alias as one more token that can match exactly. Section 7 measures this split rather than assuming it.

---

## 3. Dataset facts verified before writing retrieval code

Every claim the plan makes about the data was re-checked against `standards.csv` before any
retrieval code was written. The structural facts all held; one estimate did not.

| Check | Result |
|---|---|
| Total rows | 35,524 (24,117 current, 11,407 withdrawn) |
| Canonical rows | 35,393 canonical, 131 folded duplicates |
| Current and canonical | 24,034 rows across 23,341 base ids |
| Final index size | 23,341 — matches the planned figure exactly |
| Base ids with more than one edition | 5,437 |
| `aspect` really filled, `kys_id < 65000` | 99.7% |
| `aspect` really filled, `kys_id >= 65000` | 54.4% |

"Really filled" excludes the literal string `N/A`, which the dataset uses as a value rather than a
blank. Counting `N/A` as present overstates `aspect` coverage at 96.8%.

The 54.4% figure is why `aspect` and `group` are boosts and never filters. A hard filter on either
silently discards roughly half of the newest standards, which are exactly the 2025 and 2026 editions
a procurement tool most needs to surface.

**Source damage that can only be normalised, not repaired.** 845 titles carry a three-character
mojibake sequence where a punctuation character used to be, the result of the scrape reading UTF-8
bytes as Latin-1. The original character is already lost, and it stood for different characters in
different titles, so cleaning replaces it with a space rather than guessing a dash. A further 12
rows carry a lowercase `Is ` number prefix, normalised to `IS `. Both are display problems more than
retrieval problems, but a judge reading the output sees them.

One estimate did not survive contact with the data. The plan expects 3,711 base ids to have
differently-worded past editions, measured on raw titles. After stripping revision markers and
encoding damage, only **1,808** gain any genuinely new word. Most of the apparent difference was
"(Second Revision)" against "(Third Revision)". See section 7 for what that source is worth.

---

## 4. Pipeline

```
tender text or PDF
  -> rejoin hard-wrapped lines  a wrapped sentence is one item, not three
  -> detect Key: value specification blocks   one block is one line item
  -> split into line items      bullets, numbering, table rows, inline sub-items
  -> drop section headings
  -> strip boilerplate, extract and remove IS citations
  -> extract requirements       product, material, quantities, environment, properties
  -> BM25  +  dense bi-encoder  reciprocal rank fusion, no training required
  -> cross-encoder rerank       built, off by default, see section 7
  -> metadata boosts
  -> relevance tiers
  -> ranked candidates + resolved citations + requirements
```

### Query side, all rules

Splitting a tender is structural, not semantic. A line reading "a) hand pump b) HDPE tank c) sluice
valve" is three products, and a bullet character says so more reliably than any embedding.

Each line item is retrieved separately. Embedding a whole tender as one vector averages six products
into a point that matches none of them.

Six rules do the work:

1. **Rejoining wrapped lines.** A PDF hard-wraps prose mid-sentence, and every newline used to be an
   item boundary, so "…for the water" and "distribution network." became two searches describing
   nothing. A line joins the next only when the first has no terminal punctuation and the second
   starts with a lowercase word. Requiring that lowercase start is what stops a heading, a table row
   or a numbered item from being swallowed by the paragraph above it.
2. **Specification blocks.** Two or more consecutive `Key: value` lines are one product described
   attribute by attribute, not several products. The block collapses to a single line item whose
   query is built from the values, with the product name taken from a title line above the block or
   from a `Product`/`Item`/`Description` key. Commercial keys such as `Warranty` and `Quantity` are
   kept for display but left out of the query. This runs before line splitting, because splitting
   first destroys the structure that identifies the block.
3. **Row splitting** on newlines and semicolons. Table pipes flatten to spaces rather than splitting,
   because a table row is one line item and `|` only separates cells inside it.
4. **Sub-item splitting** on inline markers like `a)` and `2.`, refusing to split after "Part",
   "Sec", "Clause", "Table", "Grade", "Type" or "Class" so that `IS 8329 (Part 1)` stays intact.
5. **Boilerplate stripping** of procurement filler: "shall be supplied", "as per", "make/brand",
   bidder and contractor references, quantities, rates, delivery and warranty terms, "ISI marked",
   "or equivalent", tender unit codes such as `MT`, `SQM` and `RM`, and the leading serial number of
   a schedule row. Table header rows are dropped outright: searching
   `Sl Description of item Unit Qty` returned a pesticide standard, because SL is a formulation code
   in BIS titles.
6. **Citation extraction** handling `IS 1786`, `IS 1786:2008`, `IS:456-2000`, `IS 2911 (Part 1/Sec 4)`,
   `IS 8329 Part 1` and `IS/ISO 9001:2015`, normalised to `is_base_id` form.

Citations are then **removed from the query text**. They are resolved exactly against the lookup
table, and leaving the digits in the semantic query only adds noise. This also keeps the evaluation
honest: it measures description-to-standard, not citation lookup.

**Section headings are dropped rather than searched.** "NOTICE INVITING TENDER" describes no
product, so retrieving against it returns whatever happens to be nearest in vector space at a
confident score. A heading is a line that ends in a colon, or an all-caps line of six words or
fewer. A heading that cites a standard is kept, because the citation still needs resolving.

spaCy is used for noun-phrase extraction when installed, with a function-word split as fallback. The
pipeline runs fully without it.

### Requirement extraction, and what it can honestly do

Every line item is turned into a labelled object: product, material, quantities, environment,
properties, plus an `unmapped` list so nothing the officer typed is silently dropped.

```
Procure 100 stainless steel water storage tanks for outdoor installation,
minimum capacity 500 litres, resistant to corrosion

  product      water storage tank
  material     stainless steel
  environment  outdoor
  properties   corrosion resistant
  capacity     minimum 500 L
```

The order quantity of 100 is deliberately not captured. It has no unit, and reading it as a capacity
would be worse than reading nothing.

**This is for explanation, not for ranking, and the numbers say why.** Counted over the 23,341
indexed titles with the mined gazetteers:

| Attribute vocabulary | Titles containing any |
|---|---|
| material | 15.6% |
| environment | 2.4% |
| property | 2.1% |
| numeric specification | 1.6% |

Capacity, operating temperature and installation environment live in clause 4 of the standard's PDF,
which this dataset does not carry. A requirement-match score computed against indexed text is
therefore near zero for most candidates, and a "scope match" component cannot exist at all. Section
7 records what happened when the boost was built and measured anyway.

What extraction does earn: the officer sees what was understood before seeing standards, and a
specification block retrieves as one clean product query instead of five disconnected attribute
searches.

Four extractors run in order of reliability. Pre-labelled `Key: value` pairs need no inference at
all, since the key names the field. Quantities are regex over number and unit, handling qualifiers
("minimum", "not less than", "up to"), ranges ("8 mm to 32 mm"), unit-first notation ("DN 150") and
Indian digit grouping ("1,00,000"). Materials, properties and environments are gazetteer lookups,
longest match first so "stainless steel" beats "steel". The product is the head phrase, taken before
the first comma or preposition.

### Gazetteers are mined, not hand-written

`data/gazetteers/*.txt` is generated by `05_mine_gazetteers.py` from `title_clean` across the
indexed corpus: 139 material terms, 35 property, 18 environment. Seeds and head words drive the
mining, corpus frequency filters it, and a documented review list removes candidates that read like
properties but are measured laboratory quantities, so a tender asking for a "corrosion resistant"
tank cannot match a standard about insulation resistance testing.

Alongside each generated file sits a hand-maintained `*_manual.txt`, merged at load time and never
overwritten: 25 material, 22 property, 20 environment. These are the procurement shorthand the
corpus cannot supply, because a tender writes "GI pipes", "SS 304" and "FRLS cable" where a BIS
title spells the material out or omits it. It is the same reasoning as `data/aliases.csv`, applied
to attributes rather than to standards.

Hand-writing these lists would repeat the circularity section 7 flags for `data/aliases.csv`: the
author's vocabulary rather than BIS's. A gazetteer derived from BIS titles matches words that are
actually in the index. `*_manual.txt` files are merged in at load time and never overwritten, for
terms the corpus cannot supply.

### Retrieval side

**Hybrid, fused with reciprocal rank fusion** (`k = 60`), which needs no training data. Dense
retrieval alone fails on exact identifiers and on near-identical titles separated only by a size or
pattern name; keyword retrieval alone fails on phrasing that shares no words with the title.

**Metadata as boosts, never filters.** Product specifications gain 0.06, methods of tests lose 0.03
but stay reachable, mandatory certification gains 0.03, and recency adds up to 0.02 on a linear
ramp from 1980.

**Cited standards are pinned above the ranked results.** A cited, still-current standard scores 1.0;
parts of a cited standard that has since been split score 0.95, up to three parts per citation.

---

## 5. Worked example: a citation that no longer exists

A tender line reading "Structural steel angles and channels for roof trusses, hot rolled, conforming
to IS 2062" hits a case the dataset contains for real. IS 2062:2011 is withdrawn, and BIS split the
standard into parts in 2025 and 2026. The output reports all of it:

```
cited IS 2062 [withdrawn] cited standard is withdrawn; not recommended,
      pass on for its replacement; it was split into IS 2062 (Part 1), IS 2062 (Part 2)
      replaced by IS 2062 (Part 1):2025
  1. 0.950  IS 2062 (Part 1):2025   Structural Steel - Part 1 - Hot Rolled Medium and High tensile Steel
  2. 0.950  IS 2062 (Part 2):2026   Structural Steel - Part 2 - Hot Rolled Quenched and Tempered Plates
```

A bare cited number has to reach the parts that replaced it, because tenders keep citing the old
number for years. That is what `successor_parts` does.

---

## 6. Models and build

| Component | Model | Notes |
|---|---|---|
| Bi-encoder, primary | `BAAI/bge-small-en-v1.5` | every line that reaches retrieval in English: English input and anything translated. 384 dimensions |
| Bi-encoder, fallback | `intfloat/multilingual-e5-small` | only lines still in a non-Latin script at retrieval (translation off, unavailable or failed). ~100 languages, 384 dimensions, loaded on first use. Section 7 has why there are two |
| Cross-encoder | `cross-encoder/ms-marco-MiniLM-L-6-v2` | built and wired, off by default |
| Keyword | `rank_bm25` Okapi | tokenizer now keeps Indic and Arabic script (section 14) |
| Vector search | `faiss-cpu`, numpy fallback | 23,341 × 384 floats is ~35 MB, so exhaustive search is viable either way |
| Translation | `facebook/nllb-200-distilled-600M`, `ai4bharat/indictrans2-*-dist-200M` | query side and answer side, CPU, downloaded on first non-English query (section 14) |

Embedding 23,341 documents took **468.8 seconds** on CPU across 365 batches. That is the only slow
step in the build; everything else finishes in four to eight seconds. With scope text embedded, the
documents are longer (median 61 words for the 11,280 with scope text), and the full build took
575.8 seconds. The multilingual fallback vectors are a second pass over the same text with e5,
which is several times slower on CPU: a full build embedding with e5 alone took 2,115.8 seconds on
the same machine. `--no-fallback` skips
that pass, at the cost of untranslated non-English lines falling back to the English encoder.

The embedding step is the one figure that moves a lot with the machine and the `torch` build. A
second CPU machine running the fallback pins in section 1 took **1,518.7 seconds** for the same 365
batches, roughly 3x slower, and produced a byte-identical index shape of 23,341 x 384. Treat 468.8 s
as a floor rather than an expectation, and budget up to half an hour on an unknown CPU.

**The bi-encoder needs both of its prefixes, and this is easy to get silently wrong.** e5 is
asymmetric: `"query: "` on the query side, `"passage: "` on the document side, and omitting the
document prefix costs retrieval quality without failing. The prefixes now come from
`is_advisor/config.py` rather than from sniffing the model name - the old test (`"bge" in
config.BI_ENCODER`) applied *no* prefix at all the moment the encoder was swapped for a non-bge one.
The prefix is applied at encode time, not stored in `doc_text`, so the corpus parquet, the keyword
index and the stale-vector fingerprint all still describe the real document text.

**The stale-vector guard now also compares the encoder.** The fingerprint alone could not see an
encoder swap: the document text does not change, so the hash matches, and `embeddings.npy` is left
with the right shape and the wrong meaning. Comparing a multilingual query vector against
English-encoder document vectors returns confident nonsense, which is the worst failure mode
available, so `index_meta.json` records the model name and `search.py` refuses vectors built by a
different one.

### Artifacts

`artifacts/` is derived, and it is **committed anyway** - a deliberate trade so a fresh clone can demo
without first waiting up to 25 minutes for a build. `01_build_index.py` rebuilds all of it, and the
rebuild has to be committed too whenever `standards.csv` or `config.BI_ENCODER` changes. Missing that
recommit degrades quietly rather than loudly: the loader compares the stored text fingerprint *and*
the encoder name in `index_meta.json`, warns, and falls back to keyword-only.

| File | Contents |
|---|---|
| `corpus.parquet` | the 23,341 indexed documents with both text fields and the scope text |
| `lookup.parquet` | all 35,524 rows for citation resolution |
| `bm25.pkl` | pickled keyword index |
| `bm25_scope.pkl` | keyword index over scope text alone, 11,280 documents; loaded but off by default |
| `embeddings.npy` | 23,341 × 384 float32, primary encoder (bge-small-en) |
| `embeddings_multilingual.npy` | 23,341 × 384 float32, fallback encoder (multilingual-e5-small), same text |
| `index_meta.json` | fingerprints, document count, model name |
| `eval_results.csv`, `vocabulary_ablation.csv` | last measurement run |

**Stale-vector guard.** `index_meta.json` stores a hash of the embedded text. Rebuilding the corpus
with `--no-dense` after the document text changes would leave vectors describing rows that have
moved, so the loader compares fingerprints, prints a warning and falls back to keyword-only rather
than returning quietly wrong rankings. This was tested by corrupting the fingerprint deliberately;
it fires and degrades cleanly.

### Configuration

All knobs live in `is_advisor/config.py`:

| Setting | Value | Meaning |
|---|---|---|
| `BM25_TOP_K`, `DENSE_TOP_K` | 50 | candidates pulled from each retriever |
| `FUSION_TOP_K` | 50 | size of the fused list |
| `RRF_K` | 60 | rank-fusion damping |
| `FINAL_TOP_K` | 10 | library default for candidates returned; `03_search.py` asks for 5 |
| `USE_RERANKER` | `False` | cross-encoder off by default |
| `USE_SCOPE_RETRIEVER` | `False` | scope-text keyword index as a third fused list, off by default |
| `SCOPE_TOP_K` | 50 | candidates pulled from the scope index when it is on |
| `SCOPE_MIN_TITLE_OVERLAP` | 0.35 | quality gate on scope rows |
| `BOOST_PRODUCT_SPEC` | 0.06 | product specifications over test methods |
| `BOOST_METHODS_OF_TESTS` | −0.03 | mild demotion, still reachable |
| `BOOST_MANDATORY_CERT` | 0.03 | — |
| `BOOST_RECENCY_MAX` | 0.02 | linear from `RECENCY_FLOOR` = 1980 |
| `SCORE_CITED` | 1.0 | explicitly cited standard |
| `SCORE_CITED_PART` | 0.95 | part of a cited, since-split standard |
| `MAX_PINNED_PARTS` | 3 | cap on parts pinned per bare citation |
| `MULTILINGUAL` | `True` | detect the input language, translate it, answer in it |
| `DEFAULT_LANGUAGE` | `None` | `None` detects per document; a code forces both directions |

---

## 7. Measured results

Two evaluation sets, and they disagree by a wide margin (section 8):

- **`data/eval_set.jsonl`, 121 hand-written items.** Phrased by someone reading BIS titles. This is
  an upper bound and a regression guard.
- **`data/eval_tenders.jsonl`, 86 real tender BOQ lines.** The procurement officer's own wording,
  with the cited standard as gold. This is the closer estimate of field accuracy.

| Shipping default (hybrid) | Recall@1 | Recall@5 | Recall@10 | MRR |
|---|---|---|---|---|
| hand-written set | 0.727 | 0.917 | 0.959 | 0.810 |
| **real tender lines** | **0.395** | **0.605** | **0.709** | **0.470** |

**Quote the second row.** The first is what the system does on text written to resemble its index.
No query in either set contains its own IS number. **Read section 8 before quoting any of these
numbers.**

### Real tender lines (`02_evaluate.py --ablate --set tenders`)

| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR | R@5 without word splitting | R@5 before scope text |
|---|---|---|---|---|---|---|
| keyword only | 0.244 | 0.465 | 0.547 | 0.337 | 0.407 | 0.407 |
| scope keyword index only | 0.140 | 0.337 | 0.372 | 0.221 | 0.326 | — |
| dense only | 0.372 | 0.570 | 0.640 | 0.457 | 0.558 | 0.430 |
| **hybrid, shipping default** | **0.384** | **0.593** | **0.709** | **0.464** | 0.581 | 0.488 |
| hybrid + scope keyword index *(off)* | 0.302 | 0.523 | 0.663 | 0.392 | 0.465 | — |
| keyword + reranker | 0.302 | 0.523 | 0.605 | 0.387 | 0.488 | — |
| dense + reranker | 0.267 | 0.512 | 0.663 | 0.377 | 0.500 | — |
| hybrid + scope keyword index + reranker | 0.291 | 0.570 | 0.674 | 0.403 | 0.570 | — |

The last two columns are the same configuration one step back: without the query-side word
splitting described below, and additionally on the index built before scope text (loaded from a copy
of the old artifacts, and measured without word splitting). Keyword-only is identical in those two
columns, as it should be: the keyword text of the index did not change.

What real text says that the hand-written set could not:

- **Dense retrieval beats keyword retrieval on real text, and by a lot.** 0.570 against 0.465
  Recall@5. On the hand-written set it is the other way round (0.843 against 0.917), because those
  items share words with BIS titles. The hybrid default was shipped against the hand-written
  measurement on exactly this argument, and real text now backs it.
- **Scope text is worth about 9 points of Recall@5 on real text.** Measured before word splitting,
  hybrid went from 0.488 to 0.581, and dense-only from 0.430 to 0.558. That is larger than the gain on the hand-written set, as
  `SCOPE_TEXT.md` section 5 predicted.
- **The separate scope keyword index still makes things worse** (0.593 to 0.523), so keeping it off
  holds on real text too. The reranker also stays below the default.
- **Run-together PDF text was a large loss, and word splitting recovers part of it.** 28 of the 86
  items came out of their PDF with the spaces gone ("Supplying,installing,testingandcommissioningof
  GIpipes"), and scored 0.464 Recall@5 against 0.638 for the other 58.

### Word splitting on the query side (`is_advisor/wordsplit.py`)

`strip_boilerplate` now re-inserts the lost spaces before anything else reads the query: dynamic
programming over each long run of letters, choosing the split whose words are most frequent in our
own corpus (titles, classification path, scope text) plus a short list of procurement verbs. No model
and no download. On the shipping default:

| Real tender lines, hybrid | Recall@1 | Recall@5 | Recall@10 | MRR | glued lines R@5 (28) |
|---|---|---|---|---|---|
| without word splitting | 0.302 | 0.581 | 0.674 | 0.403 | 0.464 |
| **with word splitting** | **0.384** | **0.593** | **0.709** | **0.464** | **0.536** |

The hand-written set is unchanged at the default (it has no run-together text); dense-only moved
from 0.835 to 0.843 Recall@5.

The first version measured *worse* at Recall@5 (0.558), and the reason is worth recording. It also
split misspellings: "treatement" became "treat em ent", "construcion" became "constru ci on",
because OCR'd scope text puts fragments like "ent" and "ion" in the vocabulary about as often as
real words like "tee" and "pvc". Two guards fixed it. Pieces of three letters or fewer must come
from a whitelist of function words and tender abbreviations (gi, ms, di, tmt, fe, mm, ...), and a
split whose pieces average under four letters is rejected as a misspelling. Genuinely glued text
averages about five. Misspellings are now left exactly as written.

These guards were shaped while looking at the same 86 items the gain is measured on. The rules are
generic, not item-specific, but treat the gain as optimistic until a fresh set of tender lines
confirms it.

### Hand-written set (`02_evaluate.py --ablate`)

"Family R@5" is Recall@5 on the 12 items from the nine miss families named in
`data/SCOPE_TEXT.md` section 1 (`02_evaluate.py --families`).

| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR | Family R@5 | sec/query |
|---|---|---|---|---|---|---|
| keyword only | **0.810** | **0.917** | **0.959** | **0.862** | 0.583 | 0.05 |
| scope keyword index only | 0.430 | 0.537 | 0.595 | 0.484 | 0.250 | 0.02 |
| dense only | 0.636 | 0.843 | 0.901 | 0.731 | 0.500 | 0.04 |
| hybrid, shipping default | 0.727 | **0.917** | **0.959** | 0.810 | 0.667 | 0.08 |
| hybrid + scope keyword index *(built, off)* | 0.521 | 0.752 | 0.868 | 0.631 | 0.500 | 0.10 |
| keyword + reranker | 0.595 | 0.876 | 0.926 | 0.713 | **0.750** | 1.13 |
| dense + reranker | 0.587 | 0.851 | 0.909 | 0.698 | 0.667 | 1.18 |
| hybrid + scope keyword index + reranker | 0.587 | 0.851 | 0.876 | 0.694 | 0.667 | 1.25 |
| hybrid + requirement boost *(built, measured, removed)* | 0.717 | 0.883 | 0.942 | 0.784 | — | 0.13 |

Every row but the last was re-measured together on the 121-item set, against the index built with
scope text embedded, and after the two gold labels corrected in section 8 (IS 2556 and IS 10124).
That relabel alone moved the default from 0.909 to 0.917 Recall@5: the IS 10124 item became a hit.
It is a correction of the answer key, not a retrieval gain. The requirement-boost row cannot be re-run, because the code it measures was
deleted; it is left here at its original 120-item figures as the record of why it was deleted, and
should be compared against the 120-item hybrid numbers it was measured beside
(0.725 / 0.883 / 0.942 / 0.794), not against the rows above it.

The `sec/query` column is machine-dependent, so read it as ratios rather than absolutes. The
reranker's cost relative to the retrieval it re-sorts is the part that travels: roughly 15x the
shipping default, and 20x keyword-only.

### Scope text (clause 1)

Measured before and after the full rebuild, shipping default configuration, on the hand-written set
**before** the section 8 relabel (the real-tender comparison is in the first table of this section):

| Index | Recall@1 | Recall@5 | Recall@10 | MRR | Family R@5 |
|---|---|---|---|---|---|
| before: titles and classification only | **0.719** | 0.876 | 0.934 | 0.787 | 0.333 (4/12) |
| after: scope text in the embedding | 0.711 | **0.909** | **0.959** | **0.796** | **0.583 (7/12)** |

**Scope text in the embedding is a clear win.** The miss families are where it was supposed to help,
and they are where it helped. IS 1554 "armoured LT power cable" went from rank 10 to 2, IS 2556 from
6 to 5, IS 7098 from 3 to 2, and dense-only Recall@10 rose from 0.868 to 0.901. Recall@1 fell by one
item, which is inside the noise of a 121-item set. As `SCOPE_TEXT.md` section 5 predicted, the
hand-written set understates this: its items are phrased close to BIS titles, which is the case
scope text is least needed for.

**IS 458 is fixed, and by exactly what section 8 said was missing.** The query says "reinforced
cement concrete pipes"; the title says "Precast Concrete Pipes (with and without Reinforcement)". The
scope reads "requirements for reinforced and unreinforced precast cement concrete pipes … used for
water mains, sewers, culverts and irrigation". It was not in the top 10 before and is now rank 5.
Nothing was tuned for it. The item stays in the evaluation set as the record of the fix.

**A separate keyword index over scope text makes retrieval worse, so it is off by default.** It was
the recommended integration in `SCOPE_TEXT.md` section 4. As a third list at equal weight in rank
fusion, it dropped Recall@5 from 0.909 to 0.736 and Recall@1 from 0.711 to 0.496. On its own it
reaches only 0.529. The argument for it was that a standard without scope text is simply absent from
its list and loses nothing. That part holds. What it missed is the other side: the list covers 48%
of the index, and for most queries its top ranks are standards that mention a query word in passing.
At equal weight, that vote lifts them over the right answer. It stays built behind
`USE_SCOPE_RETRIEVER` for re-measurement against real tender text; a down-weighted list is the obvious
variant, and it is worth fitting only on a larger evaluation set than this one.

**The reranker reads scope text too, and improves because of it.** `keyword + reranker` rose from
0.826 to 0.860 Recall@5 with no change to the keyword side: the cross-encoder scores the embedded
text, which now says what the standard covers. It is still below the shipping default.

### What the multilingual encoder changed, on English input

The bi-encoder swap (section 14: `BAAI/bge-small-en-v1.5` → `intfloat/multilingual-e5-small`) and the
Unicode-aware keyword tokenizer had to be measured on the English evaluation set before anything
could be claimed about them, because a multilingual model earning its place on non-English input
while quietly costing English recall would be a bad trade made invisibly.

| Configuration | Before (bge-small-en) | After (multilingual-e5-small) |
|---|---|---|
| keyword only, R@1 / R@5 / R@10 | 0.793 / 0.909 / 0.950 | 0.793 / 0.909 / 0.950 |
| dense only, R@1 / R@5 / R@10 | 0.645 / 0.826 / 0.868 | **0.686 / 0.843 / 0.884** |
| hybrid, R@1 / R@5 / R@10 | 0.719 / 0.876 / 0.934 | **0.744 / 0.884 / 0.967** |

Two things worth stating plainly:

- **The keyword numbers are identical**, to three decimals, even though the tokenizer changed and 65
  of the 23,341 indexed documents now tokenise differently. None of those 65 sits in the path of any
  of the 121 items. The change was still worth measuring rather than assuming, and this is what
  measuring it bought: the confidence to say "identical" instead of "should be fine".
- **Dense retrieval got better on English**, not worse: +0.041 Recall@1, +0.017 Recall@5, and hybrid
  Recall@10 moves 0.934 → 0.967. The multilingual model was adopted because it is the only way to
  serve a Hindi query at all, so improving the English case was not the argument for it - but it
  removes the trade-off this section was expecting to have to report.

The `sec/query` column is machine-dependent and was re-measured on a slower CPU than the rest of this
file was written on, so read the column as ratios rather than absolutes. The reranker's cost relative
to the retrieval it re-sorts is the part that travels: roughly 16x the shipping default, and 30x
keyword-only. One caveat on reading the column at all: a first run of this table, taken while an
unrelated job was competing for the CPU, put hybrid + reranker at 5.9 s/query rather than 1.8. The
figures above come from a run with the machine to itself, and the recall columns were identical
across both runs, retrieval being deterministic.

### Two encoders: what real tender lines said about the swap

The swap above was measured on the hand-written set, where it helped. The real-tender set did not
exist yet. Once both changes met - the multilingual encoder and clause 1 scope text - all four
combinations were built from the same corpus and measured on both sets (shipping hybrid, current
query side including word splitting):

| Encoder | Scope text | Hand-written R@5 | Real tender R@1 | Real tender R@5 | Real tender R@10 |
|---|---|---|---|---|---|
| bge-small-en | no | 0.893 | 0.256 | 0.488 | 0.616 |
| multilingual-e5-small | no | 0.901 | 0.221 | 0.430 | 0.558 |
| multilingual-e5-small | yes | **0.934** | 0.349 | 0.465 | 0.570 |
| **bge-small-en** | **yes** | 0.917 | **0.395** | **0.605** | **0.709** |

(The first row was measured before word splitting existed; the other three with it.)

**On English that reads like BIS titles, e5 is slightly better; on real procurement English it is
clearly worse.** Its dense half is where the difference sits: dense-only Recall@5 on real tender
lines is 0.279 for e5 without scope text against 0.430 for bge, and 0.430 against 0.570 with it.
Scope text helps both encoders, and the encoder choice matters more.

That would be an argument for dropping e5, except that e5 is doing a different job. The multilingual
layer (section 14) translates every non-English line to English before retrieval, so the English
encoder serves Hindi through translation. What only e5 can do is match a line that is **still** not
English when it reaches retrieval - translation switched off, its model not downloaded, or a line it
failed on. So both are kept, and each line picks one:

- **bge** for every line whose search text is Latin script: English, translated, and romanised Indic
  (which is searched as typed on purpose, and which the curated trade names catch through BM25).
- **e5** for a line whose search text is still at least 30% non-Latin letters.

The choice is made from the text, not from the item's `translated` flag: the glossary appends English
hints, so the English rendering differs from the raw line even when nothing was translated, and the
flag reads true. With translation switched off, untranslated Devanagari lines route to e5 and it
earns its place:

| Untranslated line | English encoder, top 3 | Multilingual fallback, top 3 |
|---|---|---|
| पीने के पानी के लिये डक्टाइल आयरन पाइप (DI pipe, drinking water) | IS 4985, IS 13592, IS 3589 | **IS 8329**, IS 4985, IS 3589 |
| सीमेंट 43 ग्रेड (43-grade cement) | IS 16353, IS 8043, IS 6452 | IS 8043, **IS 269**, IS 4031 (Part 14) |
| आरसीसी कार्य के लिये टीएमटी सरिया Fe500D (TMT bars) | **IS 1786**, ... | **IS 1786**, ... |

Three lines are a demonstration, not a measurement; a Hindi evaluation set is still the missing piece
(section 14). Building that comparison also exposed a bug that had been deleting Indic vowel signs in
`strip_boilerplate` ("आरसीसी कार्य" became "आरस स क र य"), the same trap the tokenizer fix in section
14 describes. It is fixed; English text is unaffected, since the only characters it now keeps are
combining marks.

The cost of keeping both is one more 35 MB vector file and, only when a non-English line actually
arrives, ~0.5 GB of memory for the second model.

### Vocabulary sources (`04_ablate_vocabulary.py`, keyword retrieval)

| Corpus | Recall@1 | Recall@5 | Recall@10 |
|---|---|---|---|
| title + classification only | 0.686 | 0.802 | 0.868 |
| + past-edition vocabulary | 0.694 | 0.802 | 0.868 |
| + curated trade names | 0.793 | **0.909** | **0.950** |
| both, shipping default | 0.793 | **0.909** | **0.950** |

### Relevance tiers (`06_calibrate_tiers.py`)

Thresholds fitted so that most correct answers reach the top tier without it swallowing the list.
Fitted values: `Highly relevant` at 0.95 and above, `Related` from 0.82, fitted to the shipping
configuration (bge-small-en primary encoder, scope text, word splitting).

| Tier | Share of gold answers landing there |
|---|---|
| Highly relevant | 69.5% |
| Related | 25.0% |
| Possibly relevant | 5.5% |

4.7% of non-gold candidates reach the top tier. That is an upper bound on the false-positive rate
rather than a measurement of it, because many of those are genuinely applicable standards that the
evaluation set simply does not name as the single right answer.

**They are re-fitted whenever the encoder changes, and they move.** The e5 swap took them from
0.96 / 0.84 to 0.95 / 0.68, and returning to bge as the primary encoder took them to 0.95 / 0.82. A
new encoder produces a different score distribution, so thresholds fitted to the old one stop meaning
what they were fitted to mean - the tier boundary drifts relative to the answers it was supposed to
separate. Nothing about ranking changed; the tiers are presentation over the existing score. The
visible effect of the e5 fit was more gold answers in the top tier (72.9% against 64.9%) and more
non-gold too (4.6% against 2.8%), the same trade the fit has always been making. Re-running
`06_calibrate_tiers.py --apply` is part of changing the encoder, not an optional follow-up. The tiers
are still fitted to the hand-written set, whose scores the real-tender set shows are optimistic; they
should move to real tender lines once that set is large enough to fit on.

### What these say

**The cross-encoder makes retrieval worse, so it is off by default.** It costs Recall@5 in every
pairing, and between sixteen and thirty times the latency. The obvious explanation is that it scores the embedded
text, which deliberately excludes the trade names and mined wording the keyword index matched on, so
it re-sorts using less information than the retriever that produced the list. That was tested
directly and it is not the cause: rescoring on a prose-formatted document instead of the
pipe-delimited one moved Recall@5 from 0.833 to 0.850, still far below keyword-only retrieval. The
model is a general MS MARCO passage ranker being asked to judge eight-word titles, which is not what
it was trained for. It stays built and wired behind `--rerank`, and deserves re-measurement against
a real tender corpus, ideally with a reranker suited to short documents.

The effect is visible on a single query. "Cast iron sluice valve DN 150 for water works" ranks
IS 14846, *Sluice valve for water works purposes*, first by default. Turn the reranker on and it
falls to third, behind an air relief valve and a screw-down stop valve:

```
python 03_search.py "Cast iron sluice valve DN 150 for water works" --rerank
  1. 0.912  IS 14845:2000   Resilient seated cast iron air relief valves for water works
  2. 0.906  IS 9338:2013    Cast iron/S.G. Iron/Cast Steel screw-down stop valves
  3. 0.858  IS 14846:2000   Sluice valve for water works purposes (50 to 1200 mm)
```

**The requirement-match boost was built, measured, and deleted.** A small lift when a requested
material or property appeared in a candidate's indexed text was the obvious way to turn extracted
requirements into ranking signal. Measured on the 120-item set, it left Recall@5 at 0.883 and
Recall@10 at 0.942, both identical to the plain hybrid retrieval it was measured against, and cost
Recall@1 (0.725 to 0.717) and MRR (0.794 to 0.784). So the code
is gone rather than kept as an unmeasured feature. The reason is the coverage table above: 85% of
indexed titles name no material at all, so for most candidates the boost has nothing to fire on, and
where it does fire it mostly rewards standards the retriever had already ranked. Requirements are
still extracted and reported; they simply do not move the ranking. This is the second honest
negative in this section, and the second time the measurement contradicted the plan.

**Past-edition vocabulary earns almost nothing.** It is the plan's highest-rated offline source, and
on its own it moves Recall@1 by 0.008 and Recall@5 not at all. On top of the trade names it changes
nothing either. An earlier draft of this table showed it costing one item (0.917 to 0.909), but the
0.917 was a 120-item figure left over from before the set grew to 121. Re-measured on 121 items, both
rows read 0.909. The honest reading is "no measured benefit", not "small benefit" and not "small
cost". Proper title cleaning is what shrank it, as described in section 3.

**Curated trade names look like the largest single win, and that number is partly circular.** The
same person wrote `data/aliases.csv` and the evaluation items, so items phrased "GI pipes" or "paver
block" are matched by aliases written with those words in mind. The direction is real, because trade
names genuinely appear in no BIS text, but +0.115 Recall@5 overstates what unseen tenders will give.

**On the hand-written set, dense retrieval alone still loses to keyword retrieval, and hybrid now
ties it. On real tender text the order reverses.** The hand-written items were written by someone
reading BIS titles, so lexical overlap with those titles is unusually high, which is exactly the
condition keyword search wins under. There, hybrid ties keyword-only at Recall@5 (0.917) and Recall@10
(0.959), and keyword-only still wins Recall@1 (0.810 against 0.727). On the 86 real tender lines,
keyword-only falls to 0.465 Recall@5 while dense reaches 0.570 and hybrid 0.593. Hybrid stays the
default, and a non-English query has no keyword path at all until it is translated
(section 14); `03_search.py --no-dense` switches to keyword-only.

### What still misses

On the hand-written set, 10 of 121 items miss at rank 5 under the shipping default, down from 15
before scope text. Four of the five were fixed by scope text and one by correcting its label
(IS 10124, section 8):

- IS 1367 (Parts 10, 13), threaded fastener supply conditions
- IS 13730 (Part 31), glass-fibre-covered winding wires
- IS 2062 (Part 1), "structural steel sections for roof trusses"
- IS 8329, "DI pipes with socket and spigot ends"
- IS 1239 (Part 1), IS 17633, IS 16049, IS 13010, IS 383, IS 10701: single items outside the two
  patterns below

**Multi-part standards where the query names the family, not the part.** A procurement officer
writes "armoured LT power cable"; the dataset holds a dozen near-identical part titles, and nothing
in a title says which part covers which case. Scope text fixed the IS 1554, IS 2556 and IS 7098
items. What remains is mostly outside its reach:

- **IS 1367 and IS 13730** are adoption-heavy families; only 3 of 22 and 5 of 43 parts have scope
  text, and IS 13730 (Part 31) has none.
- **IS 10124** was a labelling error, not a retrieval one. Its twelve sibling parts carry
  near-identical scopes, and the query asks for "sockets and bends"; bends are Parts 8 to 13, and
  those were exactly the parts ranked above the gold Part 2. The gold now lists the socket and bend
  parts, and the item ranks first (section 8).

**Descriptive phrasing that dilutes a short alias hit.** "Supply of DI pipes with socket and spigot
ends for the water distribution network" does contain the alias "DI pipe", and "DI pipe" on its own
ranks IS 8329 first. In the full line the surrounding words match many pipe standards at once, and
the alias-bearing document is itself long, since it carries the title, the classification path, the
mined vocabulary and the alias list. BM25 length normalisation then works against the very document
the alias was added to promote. Gold falls to rank 6 on keyword retrieval and below rank 5 under
fusion.

This is the cost side of the alias list, and it is worth knowing before adding hundreds more rows.
Aliases buy exact matches on trade names and pay for them in document length. Keeping the alias
field short, or weighting fields separately instead of concatenating them, is the obvious thing to
try next.

Note that the miss list printed by `02_evaluate.py --ablate` comes from the last configuration in
the table, not the default. Run it without `--ablate` for the default configuration's misses.

On real tender lines, 35 of 86 miss at rank 5 (`02_evaluate.py --set tenders --show-misses 40`).
Beyond run-together text that the splitter cannot repair, many misses are short lines for common water-supply
fittings and building materials: "C.P. brass bib cock of approved quality" (IS 8931), "cast iron
double flanged sluice valves" (IS 14846), "TMT steel reinforcement" (IS 1786). These have not yet
been diagnosed item by item. Some cannot be explained by vocabulary alone: the IS 14846 title itself
says "sluice valve".

### What the test-tender fixes did to these numbers

The seven query-side fixes in section 10 moved the headline from 0.883 to 0.876 Recall@5, and none
of that movement came from the fixes. It is entirely the IS 458 item added as a known miss. On the
original 120 items the default configuration hits the same 106 at rank 5 and the same 87 at rank 1,
before and after. That is expected: the fixes target PDF wrapping, table scaffolding and document
headings, and the hand-written evaluation lines contain none of those.

Three things the test-tender run showed that the evaluation set cannot:

- **IS 8329 ranks first at 0.990 on the tender, but is still a miss in the evaluation set.** The
  tender writes "centrifugally cast ductile iron pressure pipes", which is the title's own wording.
  The evaluation item writes "DI pipes with socket and spigot ends" and still falls below rank 5. The
  tender result is a phrasing match, not a fix, so the miss above stands.
- **Paving blocks regressed from first to fifth.** Stripping `SQM 900` from the query was correct,
  but that unit code had been accidentally telling the embedding "paved area". Keyword retrieval
  still ranks IS 15658 first; dense retrieval dropped it from 5th to 18th, and fusion lands it 5th.
  It is left untuned rather than rescued by putting scaffolding back into the query.
- **Armoured XLPE cable returned IS 7098 Part 1, not IS 1554, and that is correct.** IS 1554 covers
  PVC-insulated cable; IS 7098 covers XLPE. The answer key was wrong, not the system. Neither
  evaluation item gold-labelled IS 1554 names XLPE, so no gold needed changing.

---

## 8. Evaluation set: read this before quoting the number

`data/eval_set.jsonl` holds 121 procurement line items, each with a verified gold standard. Every
gold `is_base_id` resolves against the built index, ids are unique, and no query contains its own IS
number.

**The items are hand-written, not scraped.** The plan calls for 100 to 200 real GeM and eprocure
line items that already say "conforming to IS xxxx", and that corpus does not exist yet. These items
use procurement phrasing and are grounded in real BIS titles, but they were authored by someone who
had the answer in front of them, which biases lexical overlap upward. Treat the numbers as an upper
bound and a regression guard, not as field accuracy.

Coverage spans construction, electrical, water, mechanical, chemicals, food, textiles, medical,
metals, safety, furniture and consumer goods.

One item is in there as a **documented failure rather than a target**: RCC pipes NP3 600 mm, gold
`IS 458`. The tender says "reinforced cement concrete" and the title reads "Precast Concrete Pipes
(with and without Reinforcement)", so the query and the document share almost no words. It sits in
the set to keep that gap visible. Tuning retrieval to rescue one item would be fitting to the test.

**It has since been fixed, and it stays in the set as the record of the fix.** Nothing was tuned for
it. Adding clause 1 scope text to the embedded text moved it from outside the top 10 to rank 5,
because the scope says "reinforced and unreinforced precast cement concrete pipes" outright
(section 7). A documented failure that was later fixed for a stated reason is stronger evidence than
one that was never recorded.

That item is id 121, and it was added after the first measurement pass. Every figure in section 7 has
since been re-measured with it included, which is why the retrieval numbers there are a little lower
than an earlier draft of this file quoted: the hit counts did not change, the denominator did. It
missed at rank 10 as intended until scope text was added; at that point it cost roughly 0.008 on
each recall figure by arithmetic alone.

**Two gold labels were corrected on 2026-09-26, and each item records it in a `note` field.**
IS 2556 (Part 17) turned out, from its scope text, to cover wall-mounted bidets, while its item asks
for wash basins and water closets; the gold is now Part 4 and the water-closet Parts 2, 8, 15 and 16.
The IS 10124 item asks for "sockets and bends", but only the sockets part was gold; the bend Parts 8
to 13 were added. Part 1 (general requirements) was left out of both, since it applies to every part
and would make the items trivially easy. Only the IS 10124 correction changed a number: it turned a
miss into a hit, and section 7 says so rather than counting it as a gain.

### The real-tender set: `data/eval_tenders.jsonl`

86 line items taken from 17 public tender documents (bills of quantities and technical
specifications from MEA, MCGM, CRPF, IISc, SBI, BHEL and others), built by
`09_build_tender_eval.py` from the URL list in `data/tender_sources.txt`. Each item keeps its source
URL and its verbatim `source_text`, so every one can be checked against the original.

- **Gold is the standard the tender cites.** An engineer wrote "Providing and fixing … conforming to
  IS 15622"; the item text is that sentence with the citation removed, and IS 15622 is the answer.
  An item citing several standards (a pipe and its gasket) keeps all of them, and any one counts as a
  hit. A bare number BIS has since split into parts resolves to all the parts; a withdrawn standard
  resolves to its replacement.
- **Every item was read.** 70 were rejected by hand, each with its reason recorded in the script:
  specification prose, lists of standards, two BOQ items merged by extraction, garbled text,
  duplicates, test-method-only citations, and citations that cover a constituent rather than the
  thing procured. A further 17 were rejected by rules for constituent citations that recur across a
  whole BOQ series (every size of an "HD wire" precast drain, every anodised fitting). The rule is
  that the citation must cover what the line procures: "precast drain … HD wire to IS 432" would
  otherwise teach the evaluation that a drain is answered by a wire standard.
- **Its limits, stated plainly.** 86 items is below the 100 to 200 the plan asks for. Two documents
  supply 47 of them (an MPAKVN Indore infrastructure estimate with 28, and an MEA works BOQ with 19), and at most two items
  are kept per gold standard. The domain mix is what public BOQs contain, which is mostly civil,
  plumbing, water supply, electrical and fire work; furniture, textiles, food and medical supplies
  are barely represented, because those are procured on GeM whose bid PDFs carry catalogue
  categories rather than officer-written lines. A tender can also cite loosely (a GI pipe item citing
  IS 1239 Part 2 where Part 1 is the pipe), and the gold follows the citation regardless.
- **GeM was tried and rejected as a source.** GeM bid documents pair the buyer's own text with a
  GeM category, and many categories carry an IS number, which looked ideal. The pairing is GeM's
  loose notification match, not a label: "Steel reinforcement for R.C.C." was matched to shirts,
  tricycles and poly-pallets.

The hand-written set stays as a regression guard, and the two are reported side by side in section
7. Growing the real set is still the highest-value next task: more BOQ sources in the thin domains,
and GeM's own bid-level technical specification attachments where they carry officer-written text.
The same corpus doubles as the strongest vocabulary source available, since the words around
"conforming to IS xxxx" are the procurement officer's own phrasing for that standard.

---

## 9. Output format

One record per line item:

```json
{
  "line_item": "Ductile iron pressure pipes DN 300, K9 class, conforming to IS 8329",
  "query_text": "Ductile iron pressure pipes DN 300 K9 class",
  "requirements": {
    "product": "ductile iron pressure pipe",
    "material": ["cast iron"],
    "quantities": [{"value": 300.0, "unit": "DN", "raw": "DN 300", "field": "diameter"}]
  },
  "candidates": [
    {"kys_id": 15491, "is_number": "IS 8329:2000",
     "title": "Centrifugally cast (Spun) ductile iron pressure pipes for water, gas and sewage - Specification",
     "score": 1.0, "tier": "Highly relevant", "why": "cited explicitly as IS 8329",
     "aspect": "Product Specification", "dept_code": "MTD", "mandatory_cert": true}
  ],
  "cited_standards": [
    {"cited_as": "IS 8329", "kys_id": 15491, "is_number": "IS 8329:2000",
     "title": "Centrifugally cast (Spun) ductile iron pressure pipes ...",
     "status": "current", "in_index": true,
     "replaced_by_is": null, "successor_parts": [],
     "note": "cited standard is current; the edition shown is the latest"}
  ]
}
```

`candidates` is the ranked recommendation list and contains only current, latest-edition standards.

`cited_standards` is separate and reports what the tender named, including withdrawn standards, with
`replaced_by_is` and any `successor_parts` attached for whatever consumes the output.

`why` names the query words that actually hit the document, whether the match was semantic, and
which boosts applied, so a ranking can be explained rather than asserted.

`requirements` is what the line item was understood to ask for, in the schema described in section
4. It is reported for explanation; it does not influence `score` (section 7).

`score` runs 0 to 1 against a fixed ceiling: the value a candidate would reach if every active
retriever ranked it first and it collected every boost. It is not a probability, but it is comparable
across queries and it does not pin the top hit at 1.000 on every search.

`tier` bands that score into `Highly relevant`, `Related` or `Possibly relevant`. The thresholds are
fitted to the evaluation set by `06_calibrate_tiers.py`, not chosen as round numbers, and they carry
every caveat of that set. Cited standards and pinned successor parts are always top tier regardless
of the thresholds, because the tender naming a standard is a fact rather than a ranking.

Cited standards and their parts are pinned above the ranked results. On a line item that cites one
number while describing a different product, those pins can fill most of a top-5 list, so ask for
more candidates when that matters.

A non-English query adds fields and changes none. `language` and `line_item_english` appear at the
item level, and `title_localized` / `why_localized` / `tier_localized` on each candidate,
`note_localized` / `status_localized` / `title_localized` on each cited standard:

Real output, abridged to one candidate, from
`03_search.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786 के अनुसार" --json -`:

```json
{
  "line_item": "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786 के अनुसार",
  "line_item_english": "TMT Saria for RCC work, according to Fe500D IS 1786 bar reinforcement steel",
  "query_text": "TMT Saria for RCC work according to Fe500D bar reinforcement steel",
  "language": {"code": "hin_Deva", "name": "Hindi", "native_name": "हिन्दी",
               "tier": "first_class", "localized": true, "titles_translated": true,
               "note": "IS numbers and official titles are kept in English; translated text is machine translation"},
  "candidates": [
    {"kys_id": 8195, "is_number": "IS 1786:2008",
     "title": "High Strength Deformed Steel Bars and Wires for Concrete Reinforcement - Specification",
     "title_localized": "कंक्रीट प्रबलित करने के लिए उच्च शक्ति विकृत स्टील बार और तार - विनिर्देश",
     "score": 1.0, "tier": "Highly relevant", "tier_localized": "अत्यधिक प्रासंगिक",
     "why": "cited explicitly as IS 1786",
     "why_localized": "स्पष्ट रूप से IS 1786 के रूप में उद्धृत किया गया",
     "aspect": "Product Specification", "dept_code": "CED", "mandatory_cert": true}
  ],
  "cited_standards": [
    {"cited_as": "IS 1786", "is_number": "IS 1786:2008", "status": "current",
     "status_localized": "वर्तमान", "in_index": true,
     "note": "cited standard is current; the edition shown is the latest",
     "note_localized": "उद्धृत मानक वर्तमान है; दिखाए गए संस्करण नवीनतम है"}
  ]
}
```

`line_item_english` is worth reading closely, because it shows the glossary doing the job it exists
for. The translation rendered सरिया as "Saria" - a transliteration, not the trade term - and the
glossary appended "bar reinforcement steel", which is the wording the index actually carries. Section
14 covers why that hint is additive and cannot remove a term the translation got right.

`is_number` and `title` are **always** the English originals. The number is an identifier and the
title is the standard's legal name, which a tender has to quote as it stands; the localised strings
sit beside them as a reading aid, and every one of them is machine translation. For an English query
none of these keys appear at all, so an existing consumer reads exactly what it read before.

Confirm any change to this shape with whoever consumes it before wiring anything to it.

---

## 10. Bugs found and fixed while building

All of these were caught by running the pipeline on real data and reading the output. Each is now
covered by `tests/test_pipeline.py`.

| Bug | Symptom | Fix |
|---|---|---|
| Revision markers with inner spaces | `( Fifth Revision )` survived cleaning and polluted mined vocabulary | regex allows whitespace inside the parentheses |
| Encoding damage | scrape left U+FFFD and backticks mid-word, splitting tokens | junk characters stripped during cleaning |
| Sub-item splitter over-firing | `IS 8329 (Part 1)` truncated a table row at "(Part", losing the part number | split points rejected after Part, Sec, Clause, Table, Grade, Type, Class |
| Table pipes treated as boundaries | one row became several fragments, separating a product from its citation | pipes flatten to spaces; only newlines and semicolons split rows |
| Boilerplate pattern without a word boundary | "nominal size" became "minal size", "NOTICE" became "TICE", corrupting product descriptions | every alternative now ends on `\b` |
| Section headings searched | "NOTICE INVITING TENDER" returned an internships guideline at a top score | headings detected and dropped unless they cite a standard |
| Scores saturated | every top hit scored exactly 1.000 because boosts were added then clipped | boosts applied multiplicatively against a fixed ceiling |
| Qualifier detached from its number | "minimum capacity 500 litres" reported 500 L with no qualifier, because the field word sat between them | up to two words allowed between qualifier and value |
| Field word borrowed across dimensions | "32 mm diameter, quantity 45 MT" reported the tonnage as a diameter | a nearby field word is believed only when it measures what the unit measures |
| Range merge too eager | "25 mm bore and 40 mm pipe" collapsed into one 25-to-40 range | two measurements merge only when the text between them is a range connector |
| Count word inside a product name | `sets?` matched the "set" in "pump set", so the product became "pump" | a count is only a count when a number introduces it |
| Attribute stripped from the middle of a name | removing the material everywhere turned "Ordinary Portland Cement" into "Ordinary" | attributes are stripped only where they lead the phrase |
| Grade code survived the word cap | "TMT reinforcement bars Fe 500D" kept the grade because trimming ran before the five-word cap | cap first, then trim trailing specifiers |
| Consumed key reported as unparsed | the `Product` key named the product and was also listed under `unmapped` | product keys are consumed, not reported as unmapped |
| Disabled boost still counted in the ceiling | adding the requirement boost depressed every score even when it was switched off, quietly invalidating the fitted tier thresholds | the ceiling counts only boosts that are active |

### Found by running a real tender PDF

The seven below came from one run of `03_search.py --file test_tender.pdf`. All are on the query
side or in document reading; none touched retrieval, fusion, boosts or the index.

| Bug | Symptom | Fix |
|---|---|---|
| Wrapped PDF lines split into separate items | "…for the water" and "distribution network." became two searches describing nothing, roughly eight junk items in one document | lines are rejoined before any splitting when the first has no terminal punctuation and the second starts lowercase |
| Citation numbers read as quantities | "conforming to IS 269" reported a weight of 269 tonnes, and IS 2062 reported 2062 tonnes | requirements are extracted from citation-stripped text, plus a guard refusing any number directly after an IS marker |
| Leading work verb became the product | three tender lines reported `product: Providing` | an explicit leading gerund phrase is stripped, matched only at the start of the line |
| Every table row processed twice | the whole schedule of quantities appeared, and was searched, twice | one extraction path per page: `extract_text` only, which already returns table rows intact |
| "G.I." destroyed by unit matching | the row index and the G of "G.I." parsed as three grams, leaving the item to search on "I. pipes" | a unit match is refused when the letter is followed by a dot and another letter |
| Table scaffolding entered the query | `MT 120`, `SQM 900`, row indices and the header row `Sl Description of item Unit Qty` were all searched; the header returned a pesticide standard, because SL is a formulation code | unit codes and leading row indices are stripped, and an all-generic-label row is detected as a header |
| Section headings survived | `SECTION B — SANITARY AND WATER SUPPLY ITEMS` is seven words and beat the six-word all-caps cap | the cap rose to ten words and `SECTION`/`ANNEXURE`/`SCHEDULE` labels are headings at any length; a capitalised line carrying a digit stays an item |

Two are worth remembering. The boilerplate bug silently corrupted real product words in every query
and was invisible until the output was read line by line. The score-ceiling bug is subtler: it broke
nothing visibly, it just moved every score down by a few percent, which would have made the
carefully fitted tier thresholds wrong without any error appearing anywhere.

The product-name bugs share a root cause worth naming. spaCy reads "pump set for borewell" as a verb
phrase and returns "borewell" as the first noun chunk, so the extractor does not trust the parser
for this. A procurement line leads with the product and then qualifies it, and the span before the
first comma or preposition beats a parser's first noun chunk on this input shape.

---

## 11. Files

| Path | What it does |
|---|---|
| `01_build_index.py` | builds corpus, keyword index, embeddings, fingerprint metadata |
| `02_evaluate.py` | Recall@1/5/10 and MRR, with per-component ablations |
| `03_search.py` | query the index, print results or emit the JSON contract |
| `04_ablate_vocabulary.py` | rebuilds the corpus with each vocabulary source off and re-measures |
| `05_mine_gazetteers.py` | mines material, property and environment vocabulary from the corpus |
| `06_calibrate_tiers.py` | fits the relevance-tier thresholds to the evaluation set |
| `07_merge_preview_metadata.py` | folds preview reaffirmation years and ICS codes into `standards.csv` |
| `08_export_normative_refs.py` | writes clause 2 normative references as a graph edge list |
| `09_build_tender_eval.py` | builds the real-tender evaluation set from public BOQ PDFs |
| `is_advisor/config.py` | paths, model names, all retrieval and boost constants |
| `is_advisor/corpus.py` | index selection, text cleaning, mined past-edition vocabulary |
| `is_advisor/wordsplit.py` | re-inserts spaces PDF extraction lost ("testingandcommissioning") |
| `is_advisor/query.py` | specification blocks, splitting, heading detection, boilerplate, citations |
| `is_advisor/requirements.py` | product, material, quantities, environment and properties |
| `is_advisor/gazetteer.py` | loading and longest-match lookup for the mined vocabularies |
| `is_advisor/documents.py` | reading a specification from text or PDF, scanned-PDF detection |
| `is_advisor/lexical.py` | BM25 index |
| `is_advisor/dense.py` | bi-encoder embeddings, FAISS with numpy fallback, text fingerprinting |
| `is_advisor/rerank.py` | cross-encoder |
| `is_advisor/search.py` | fusion, boosts, citation resolution, output contract |
| `bis_scope_scraper.py` | fetches clause 1 and 2 from BSB Edge preview pages into `data/scope_text.csv` |
| `data/scope_text.csv` | scraped scope text, normative references, ICS codes, per-row quality status |
| `data/SCOPE_TEXT.md` | how scope text was collected, its coverage, and the integration plan |
| `data/aliases.csv` | 57 curated trade-name rows, all verified against the index |
| `data/eval_set.jsonl` | 121 hand-written evaluation line items, all gold answers verified |
| `data/eval_tenders.jsonl` | 86 real tender BOQ lines with source URL and verbatim text |
| `data/tender_sources.txt` | the tender PDFs the real set is built from |
| `data/normative_refs_edges.csv`, `data/NORMATIVE_REFS.md` | clause 2 edges and the handoff note for the graph workstream |
| `data/gazetteers/` | generated attribute vocabularies, plus hand-maintained `*_manual.txt` |
| `data/sample_tender.txt` | demo tender exercising splitting, citations and a withdrawn standard |
| `data/sample_tender_hi.txt` | the same shape in Hindi: numbered items, a citation, a `Key: value` block, and the caseless-heading limit from section 14 |
| `../multilingual/` | shared language layer: detection, translation, glossary, localised output (its own README) |
| `tests/test_pipeline.py` | rule-based logic, index-selection traps, and every bug in section 10 |
| `../tests/test_multilingual.py` | the language layer, run without the translation models (section 14) |
| `tests/make_fixtures.py` | writes the PDF fixtures byte by byte, so tests need no PDF writer |
| `NEXT.md` | how each planned feature turned out, and what is still open |

Tests run as a plain script with no test framework: `python tests/test_pipeline.py`.

---

## 12. Verification

What was actually run, so the claims above can be checked rather than taken on trust.

| Check | Result |
|---|---|
| `tests/test_pipeline.py` | passes; covers the rule-based logic, the index-selection traps and every bug in section 10 |
| Every script end to end | `01`, `02`, `03`, `04`, `05`, `06` and the fixture generator all run clean |
| Every input path of `03_search.py` | text argument, `--file` text, `--file` PDF, stdin, `--json`, `--no-dense`, `--rerank` |
| Gazetteer counts | 139 + 25 material, 35 + 22 property, 18 + 20 environment (mined + manual), matching section 4 |
| Embedding fingerprint | matches the corpus, so no search silently fell back to keyword-only |
| Index size | 23,341 documents, one row per base id, current and canonical only |
| `tests/fixtures/tender.pdf` end to end | three line items, each gold standard at rank 1 under the shipping default |

### Clean-machine rebuild

The whole workstream was rebuilt from nothing on a second CPU machine, with no `artifacts/` directory
and none of the retrieval dependencies installed, to check that the numbers above survive leaving the
machine they were written on.

| Step | Result |
|---|---|
| `01_build_index.py --no-dense` | 8.0 s, 23,341 indexed documents and 35,524 lookup rows, both matching section 3 |
| `01_build_index.py` | 1,518.7 s on the second machine, 1,655.2 s on the multilingual encoder; `embeddings.npy` at 23,341 x 384, `backend=faiss` either way |
| `tests/test_pipeline.py` | passes, run once keyword-only and again with the dense stack present |
| `02_evaluate.py`, `04_ablate_vocabulary.py`, `06_calibrate_tiers.py` | all three re-run on the multilingual index; section 7 carries their output |
| `04_ablate_vocabulary.py` | every figure identical to the English-encoder run, to three decimals - the vocabulary sources are keyword-side and the tokenizer change did not reach them |
| `06_calibrate_tiers.py` | re-fitted from 0.96 / 0.84 to **0.95 / 0.68**: a new encoder means a new score distribution, so the thresholds drifted and were re-applied (section 7) |
| JSON contract on the PDF fixture | every field in section 9 present, three records, one per line item |
| The `--rerank` example in section 7 | reproduces to three decimal places, 0.912 / 0.906 / 0.858, on the multilingual index |
| `../tests/test_multilingual.py` | passes; 100+ checks over detection, notation protection, the glossary, the query layer and both localised contracts, with no translation model loaded |
| A live Hindi query end to end | `03_search.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786 के अनुसार"` returns IS 1786 at rank 1 (1.000, pinned as cited) with tier, `why` and citation note in Hindi, IS numbers and titles in English (section 14) |
| A live Tamil and Marathi round trip | translated into English, retrieved, and localised back; `multilingual/README.md` records what the translations actually looked like |

The fixture run is the end-to-end check worth repeating, because it exercises PDF reading, heading
removal, citation extraction, requirement extraction and ranking in one command:

```
python 03_search.py --file tests/fixtures/tender.pdf

  TMT reinforcement bars Fe 500D grade conforming to IS 1786
    1. 1.000  IS 1786:2008    High Strength Deformed Steel Bars and Wires  (cited)
  Ordinary Portland Cement 43 grade in 50 kg bags
    1. 0.996  IS 269:2015     Ordinary portland cement - Specification
  Cast iron sluice valve DN 150 for the pumping main
    1. 0.918  IS 14846:2000   Sluice valve for water works purposes
```

The third line is the one that justifies shipping hybrid retrieval against the measurement, as
section 7 argues, and it still does on the multilingual index: keyword-only ranks `IS 13349`,
*cast iron sluice **gates***, first at 0.987 with the sluice valve second at 0.947, and the dense
retriever is what puts `IS 14846` first at 0.918. It is a single line item rather than a measurement,
but it is the failure mode the evaluation set is too lexical to show. The absolute scores moved with
the encoder - which is what re-fitting the tier thresholds was about - while the ordering did not.

Two properties are asserted by tests rather than by inspection, because they are the ones that would
fail silently: that the index never holds a stale edition when a newer current one exists, and that
boilerplate stripping never eats a word out of a product description.

---

## 13. Known limits and what comes next

- **Scope text covers 48% of the index, and that is close to its ceiling.** 11,280 standards have
  usable clause 1 text from the BSB Edge previews. Adopted IS/ISO and IS/IEC standards will not get
  it from this source, because their preview carries only the National Foreword, so the adoption-
  heavy families (IS 1367, IS 13730) stay title-only. The separate scope keyword index measured
  negative at equal weight and is off (section 7); a down-weighted version is untried.
- **The real-tender evaluation set is small.** 86 items from 17 documents, skewed to civil and
  plumbing work (section 8). It is the number to quote, and growing it is still the highest-value
  next task.
- **Run-together PDF text is only partly repaired.** A third of real tender lines lose their spaces
  in extraction. Word splitting lifts those from 0.464 to 0.536 Recall@5 (section 7), still below
  clean lines; runs mixing letters and numbers ("with600mmx600mm") are left alone.
- **Under-splitting.** Prose hiding three products in one paragraph is treated as one item. The
  rules handle bullets, numbering and table rows; they cannot handle a run-on sentence.
- **Aliases cover 57 standards** of 23,341. They exist to make demo-critical products reliable, not
  to cover the corpus.
- **The cross-encoder is unproven here**, not proven useless. It needs re-measurement on real tender
  text, and a reranker trained for short documents is worth trying.
- **Requirements do not reach the ranking.** They are extracted, displayed and returned, but the one
  attempt to turn them into a ranking signal measured flat and was removed (section 7). Scope text
  now exists for 48% of the index, so matching requirements against it is the next thing to try,
  not a better boost over titles.
- **Product-name extraction is a head-phrase heuristic**, not a parser. It handles procurement
  phrasing well and will mislabel unusual sentence shapes. It is shown to the user precisely so a
  wrong reading is visible rather than silent.
- **Scanned PDFs are refused, not read.** Optical character recognition is out of scope; the file is
  reported as a scan instead of being searched as an empty string.
- **YAKE keyword ranking was not implemented.** Noun-phrase extraction covered the need, and nothing
  in the measurements suggested keyword scoring was the bottleneck.
- **No stemming and no field weighting in the keyword index.** Every field is concatenated into one
  string, so a long alias list lengthens the document and BM25 penalises it. Weighting title,
  classification and aliases separately is the most promising untried change (section 7).
- **Every measured number in this file is an English-input number.** The multilingual path (section
  14) has no measured retrieval quality of its own: the evaluation set is English, so translating a
  query and retrieving on the result is unmeasured end to end. A translated evaluation set is the
  first item in `NEXT.md` for that reason.
- **The better translation model is behind a gate.** IndicTrans2 is wired and preferred, and both of
  its checkpoints are gated on HuggingFace, so the shipping default is NLLB-200 unless `HF_TOKEN` is
  set. Section 14.
- **Two query rules go quiet on caseless scripts**, rather than firing wrongly: a wrapped Devanagari
  paragraph stays several line items, and a Devanagari heading is searched rather than dropped.
  Section 14.

---

## 14. Multilingual input and output

A specification in any of the 22 scheduled Indian languages is answered in that language.
`../multilingual/README.md` is the reference for the layer; this section is what it means for
retrieval, and what had to change here.

### Where it sits

```
tender text or PDF, any language
  -> detect the language          script decides; marker words break the ties
  -> fold Indic digits to ASCII   before splitting, so every later regex can see them
  -> split into line items        on the text as typed: bullets and colons are punctuation
  -> translate each line item     one model call for the whole tender
  -> append glossary hints        native trade terms -> the English terms the index holds
  ============================    the English pipeline from section 4, unchanged
  -> localise what is displayed   after ranking; identifiers never touched
```

The split runs **before** the translation and the translation runs **before** everything else,
and both orderings are deliberate. Splitting reads punctuation - bullets, newlines, semicolons,
pipes, the colon in `Key: value` - which is shared across scripts, so it works on the original;
translating first would hand the splitter one reflowed paragraph. Everything after splitting is
English-specific - the boilerplate patterns, the citation regex, the attribute gazetteers, the spaCy
model - so it runs on the translation. A `LineItem` therefore carries both: `raw` as typed, for
display, and `english` for retrieval.

### What was actually broken, measured rather than assumed

The starting point was narrower than "Hindi and English", and the larger of the two blockers was
not the embedding:

| Input | Before | Now |
|---|---|---|
| English | full pipeline | unchanged |
| Romanised Hindi ("TMT sariya Fe500D") | worked, through the 57 curated trade names in `data/aliases.csv` | detected as Hindi, still searched as typed, answered in Devanagari |
| Devanagari ("टीएमटी सरिया") | **failed** | translated, searched, answered in Hindi |
| Tamil, Bengali, Telugu, Urdu, ... | **failed** | translated, searched, answered in that language |

`is_advisor/lexical.py` tokenised on `[a-z0-9]+`, so `'आरसीसी कार्य के लिये टीएमटी सरिया 500डी'`
tokenised to exactly `['500']` and `'கம்பி'` to `[]`. BM25 is the **stronger** of the two retrievers
on this corpus - Recall@5 0.909 keyword-only against 0.826 dense, section 7 - so an Indic-script
query was reaching the weaker half of the system at best, whatever the embedding model could do.
Swapping only the encoder would have left that in place.

The tokenizer now keeps letters, digits and Indic combining marks. `\w` alone is not enough: Python
classifies Indic vowel signs as combining marks rather than word characters, so `\w+` cuts `के`
after the consonant. **65 of the 23,341 indexed documents tokenise differently** as a result (0.28%,
all non-ASCII characters deep inside a title), which is why section 7 was re-measured rather than
assumed to hold.

### Detection

Script-first, and not a language model, because the script is decisive for every Indian language
except the ones that share a script - Tamil text can only be Tamil. Marker words break only the
ties the script genuinely leaves open: Devanagari (Hindi, Marathi, Nepali, Sanskrit, Maithili,
Konkani, Bodo, Dogri), Bengali script (Bengali, Assamese, Manipuri), Arabic script (Urdu, Kashmiri,
Sindhi), and Latin (English, romanised Indic, other Latin-script languages).

An Indic script needs only a **10% share** of the letters to decide, not a majority: an Indic query
routinely carries English fragments (`IS 1786`, `Fe500D`, `IP66`), while the reverse is rare and
mis-routing it costs only a needless translation of text that was already English.

**Romanised input is detected and deliberately not translated.** "TMT sariya Fe500D chahiye" comes
back as Hindi with `romanised=True` and is then searched as typed, because those exact trade names
are what `data/aliases.csv` holds and what BM25 matches as tokens - the path section 7 measures at
+0.115 Recall@5. Handing it to a model trained on Devanagari would trade a measured path for an
unmeasured one. The answer still comes back in Devanagari.

### Protecting the notation

A procurement query is mostly notation and the notation decides the answer. An `IS 1786` that comes
back as `IS 1,786` stops matching the citation regex in `is_advisor/query.py`; a `Fe500D` that comes
back as `Fe500 D` stops matching the index. Two strategies, one per direction:

- **Into English**, the spans are lifted out, the prose is translated without them, and they are
  appended. A query is a bag of terms by the time BM25 and the bi-encoder see it, so position does
  not matter - and nothing can come back mangled because nothing was handed to the model.
- **Out of English**, placeholders (`@1@`, `@2@`), because a human reads that text and word order
  matters. That shape was measured, not reasoned about: letter-only placeholders were the first
  attempt and the model *transliterated* them, so `PLHA` came back as `पीएलएचए` and the IS number it
  stood for fell out of the sentence. Nine candidate shapes were run through the real model;
  punctuation-delimited numerals survive in Hindi and Tamil and letter forms do not.
  `multilingual/README.md` has the table. Anything that still does not survive is reported and
  reattached in brackets: a recommendation that silently drops its IS number is worse than one that
  reads awkwardly.

**Numbers stay inline going into English**, and that asymmetry is load-bearing. Lifting a number
separates it from its unit, and `is_advisor/requirements.py` reads a number *adjacent to* its unit,
so `500 लिटर` has to stay together to be extracted as a capacity at all.

### The output side, and what is never translated

The corpus cannot supply a non-English answer: 33,803 of the 35,524 standards are marked English,
120 bilingual and 17 Hindi. So the answer is produced, and it splits three ways.

| Kind | Treatment |
|---|---|
| Identifiers (`IS 16107 (Part 2/Sec 2):2017`) | never translated |
| Official titles | kept in English, with a machine-translated gloss beside them |
| What the pipeline wrote (`why`, notes, tier names, statuses) | translated |

The title rule is the one worth defending: a procurement officer has to quote the English title in a
tender document, so replacing it would break the artefact the tool exists to help produce. The gloss
is a reading aid and is labelled as machine translation.

Tier names and statuses go through a **curated table** where one exists and the model otherwise,
because two words out of context is where MT is weakest and where a wrong word is most visible.
Hindi is curated; other languages fall back to the model, and every localised string records which
happened.

### What it measures, on the evaluation set there is

The multilingual path has **no measured retrieval quality of its own**, because `data/eval_set.jsonl`
is English. What could be measured was whether it cost anything in English, and it did not: keyword
retrieval is identical to three decimals, dense retrieval improved (Recall@5 0.826 → 0.843) and the
shipping hybrid default improved (0.876 → 0.884, Recall@10 0.934 → 0.967). Section 7 carries the
table and the caveats.

What replaces a measurement, for now, is a worked round trip. A Hindi query returns the right standard
at rank 1 and reads back in Hindi:

```
python 03_search.py "आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786 के अनुसार"

LINE ITEM  आरसीसी कार्य के लिये टीएमटी सरिया Fe500D, IS 1786 के अनुसार
  language: Hindi (hin_Deva)
  english : TMT Saria for RCC work, according to Fe500D IS 1786 bar reinforcement steel
  cited IS 1786 [वर्तमान] उद्धृत मानक वर्तमान है; दिखाए गए संस्करण नवीनतम है
  -- अत्यधिक प्रासंगिक --
   1. 1.000  IS 1786:2008   High Strength Deformed Steel Bars and Wires for Conc  [cert]
        कंक्रीट प्रबलित करने के लिए उच्च शक्ति विकृत स्टील बार और तार - विनिर्देश
        why: स्पष्ट रूप से IS 1786 के रूप में उद्धृत किया गया
```

Two things in that output are the honest part. The translation transliterated सरिया to "Saria"
instead of producing "TMT bar", and the answer is still right because the glossary appended the trade
term and the citation was pinned - which is the layered design working, not the translation being
good. And `data/sample_tender_hi.txt`, the Hindi tender fixture, shows the caseless-script limit for
real: its title line "निविदा सूचना - जल आपूर्ति एवं भवन निर्माण सामग्री" is searched as a line item
rather than dropped as a heading, because `is_heading` recognises a heading by capitalisation and
Devanagari has no capitals. It returns tap and plug-cock standards, which is visible nonsense rather
than silent nonsense.

### Which encoder a line uses

Retrieval keeps two dense indexes over the same text and picks one per line: the English encoder
for anything whose search text is Latin script (English, translated, romanised), the multilingual
encoder for a line still mostly in another script. Translation is the main path; the multilingual
encoder is the safety net for when it is off, not downloaded, or fails. Section 7 has the numbers
behind that split.

### Cost

Batching is what makes this affordable on CPU. A tender is many short lines and an answer is a dozen
short strings, so the whole document is translated in one model call and the whole response in one
more, with everything cached by `(text, source, target)`. The first non-English query also pays the
checkpoint load.

| Model | On disk | State |
|---|---|---|
| `facebook/nllb-200-distilled-600M` | ~2.5 GB | the working default, ungated |
| `ai4bharat/indictrans2-indic-en-dist-200M` + `-en-indic-` | ~0.9 GB each | wired and preferred, **gated on HuggingFace** |

**IndicTrans2 is gated** (`gated=auto` on both checkpoints, confirmed against the HuggingFace API),
so using it needs an account, the terms accepted, and `HF_TOKEN` in the environment. It is the
better model for these languages and the only one that carries Bodo, Dogri, Konkani and Santali at
all, which is why it stays wired and preferred rather than being dropped for something ungated.
Without a token the layer runs on NLLB and says so in the RAG API's `GET /health`.

### Limits specific to this layer

- **No measured retrieval quality in any language but English.** `data/eval_set.jsonl` is English, so
  section 7 measures English input only. Translating those 121 items and having a speaker check them
  is the first item in `NEXT.md`.
- **The glossary is a seed.** 76 rows across seven languages, written only where the native term was
  confidently known - the same mined-versus-hand-written argument section 4 makes about the attribute
  gazetteers applies to it, and real multilingual tender lines are the honest way to grow it.
- **Romanised Marathi and Bengali resolve poorly.** Marker words cannot reliably separate them from
  romanised Hindi; both come back Hindi-family with a low confidence that says so.
- **Two query rules go quiet on caseless scripts.** `rejoin_wrapped_lines` needs a lowercase
  continuation and `is_heading` needs an all-caps line, so a wrapped Devanagari paragraph stays
  several line items and a Devanagari heading is searched rather than dropped. Both fail quietly
  rather than firing wrongly, which is the safer direction, and both are visible in the output.
- **A non-English `Key: value` block loses the key-names-the-field shortcut.** The keys are detected
  and displayed - the pattern accepts Indic and Arabic script - but they are not English keys, so the
  fields come from text extraction instead of from the labels.
- **Detection is per document, not per line item.** A three-word line carries almost no language
  signal while the tender it came from carries plenty, so a mixed-language tender gets one language
  for all of its items unless `--lang` overrides it.
