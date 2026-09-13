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
thresholds fitted by `06_calibrate_tiers.py` rather than guessed: 0.96 and 0.84. 64.0% of gold
answers land in the top tier, 30.7% in the middle, 5.3% in the lowest. 2.9% of non-gold candidates
reach the top tier, which is an upper bound on false positives rather than a measurement of them.

Cited standards and pinned successor parts are always top tier regardless of the thresholds.

One trap worth recording: adding a new boost to the score ceiling depresses every score and silently
invalidates fitted thresholds. The ceiling now counts only boosts that are actually active, and the
calibration was re-confirmed after item 5 was removed.

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

## Still open, and still the highest value

Both were already named in README section 13 and nothing built here substitutes for either.

1. **Replace the hand-written evaluation set with real tender lines.** Every number in this
   workstream is an upper bound until this is done, and the same corpus is the strongest vocabulary
   source available.
2. **Scope-text extraction from the standard PDFs.** Clause 1 is the missing input behind the
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
