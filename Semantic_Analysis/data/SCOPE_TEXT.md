# Scope text — implementation plan

README section 13 names clause 1 (SCOPE) as the quality ceiling. `bis_scope_scraper.py` collects
clause 1 and clause 2 for a standard and writes them to `data/scope_text.csv`.

**The source is the free BSB Edge preview page, not the PDF.** The PDF route was the original plan
and it was wrong: it needs a registered account, the file arrives watermarked to that account, and
the download sits behind an ASP.NET `__doPostBack`. The preview needs no login at all, carries the
same two clauses as HTML, and throws in ICS codes and a reaffirmation year.

Read this before wiring the output into retrieval. **The obvious integration — concatenate scope
text into the existing document string — will make retrieval worse, and section 3 says why.**

---

## 1. Stage 1 is 101 standards, not thousands

README section 7 lists six families as the dominant miss pattern: the query names the family, the
index holds a dozen near-identical part titles, and nothing in a title says which part covers which
case. Counted against the index, every family it names plus the three other cases in play is:

| Family | Parts in index | Dept |
|---|---|---|
| IS 1367 threaded fasteners | 22 | PGD |
| IS 13730 winding wires | 44 | ETD |
| IS 2556 sanitary appliances | 13 | CED |
| IS 10124 PVC fittings | 13 | CED |
| IS 7098 XLPE cable | 3 | ETD |
| IS 1554 PVC cable | 2 | ETD |
| IS 2062 structural steel | 2 | MTD |
| IS 458 RCC pipes | 1 | CED |
| IS 8329 DI pipes | 1 | MTD |
| **Total** | **101** | |

**101 standards cover every documented failure.** That is about seven minutes of fetching.
Do this before any bulk run: it tests the whole hypothesis cheaply, on the exact items
already written down as misses, and it tells you whether scope text earns the 5,000-standard effort.

```bash
pip install requests

python bis_scope_scraper.py probe   --id 8195          # look at one page first
python bis_scope_scraper.py fetch   --families         # 101 standards, ~7 min
python bis_scope_scraper.py extract --out data/scope_text.csv
python bis_scope_scraper.py report  --out data/scope_text.csv
python bis_scope_scraper.py review  --out data/scope_text.csv -n 10
python bis_scope_scraper.py review  --out data/scope_text.csv --worst -n 10
```

Only after stage 1 measures well: `--dept CED ETD MTD` is 5,481 standards, several hours.

---

## 2. How it fetches, and what not to store

The preview id cannot be built from `standards.csv`, so each standard takes two requests:

```
GET search_redirect.aspx?id=<kys_id>
  302 -> BIS_SearchStandard.aspx?Standard_Number=IS+1554+:+Part+1&id=7807
        that page contains  BIS_Preview.aspx?id=1554_1_1988_reff2020
GET BIS_Preview.aspx?id=1554_1_1988_reff2020   -> clause 1 and clause 2
```

The id is `<number>_<part>_<year>_reff<year>`, and that reaffirmation year is exactly what our data
does not have, so step 1 cannot be skipped. Verified: `1554_1_...` and `1554_2_...` are different
pages, so **the preview is per-part** — which is the whole reason this is worth doing, since six of
the misses in README section 7 are a query naming the family where the index holds a dozen
near-identical part titles.

No account, no cookie, no watermark. Still:

- **Store only clause 1 and clause 2.** Do not scrape or keep whatever else a preview shows. A
  derived retrieval index is a different thing from republishing standards, and this is a
  government-facing project where being able to state that distinction matters.
- **`cache_preview/` stays out of git.** It is a scrape cache, not source.
- **Be polite.** Two requests per standard, default 2 s apart, and the cache means a page is never
  fetched twice. Put a real contact address in `UA` before any bulk run.

**Coverage, measured on the full run** — 22,167 of 23,341 indexed standards fetched
(1,174 have no preview page at all):

| status | n | share |
|---|---|---|
| `ok` | 12,378 | 55.8% |
| `foreword_only` | 7,729 | 34.9% |
| `no_scope_heading` | 776 | 3.5% |
| `too_short` | 538 | 2.4% |
| `low_title_overlap` | 532 | 2.4% |
| `wrong_standard` | 207 | 0.9% |

**12,378 usable scopes = 53.0% of the index.** The split falls on exactly one line, whether the
standard is an international adoption:

| `equivalence` | with usable scope | n |
|---|---|---|
| Not Equivalent | 90.2% | 640 |
| Indigenous | 84.4% | 12,968 |
| Modified/Technically Equivalent | 68.7% | 754 |
| Identical under dual numbering | **5.2%** | 5,579 |
| Identical under single numbering | **2.1%** | 2,226 |

An adopted standard's preview carries only the National Foreword, because its scope lives in the
IEC or ISO text the Indian Standard incorporates by reference. This is a permanent limit of the
source, not open work, and it should be stated that way in README section 13.

By miss family: IS 2556 13/13, IS 10124 13/13, IS 7098 3/3, IS 1554 2/2, IS 2062, IS 458 and
IS 8329 all complete; IS 1367 3/22 and IS 13730 5/43, both adoption-heavy.

**Quality.** Scope length runs p25 18 / median 26 / p75 48 words. `title_overlap` is median 0.60,
p10 0.38, and **1,098 usable rows (8.9%) fall below 0.35** — that is where bad OCR and mis-scraped
pages concentrate. Exclude below 0.35 unless a review says otherwise.

**`wrong_standard` is real and was caught.** `search_redirect.aspx?id=<kys_id>` sometimes lands on
a different standard entirely — IS 13730 (Part 47) returned an LPG rubber hose specification. The
preview prints its own IS number, so every page is checked against what was requested; 207 rows were
dropped this way. Never remove that check.

**Two fields worth folding back into `standards.csv`**, both free and both better than what is
there: reaffirmation year on **11,306** standards (against roughly 1,400 today, and README section 7
notes the version checker cannot lean on the existing field), and ICS codes on **14,959** where the
dataset has none. Plus UDC on 6,514 older standards, which use that scheme instead.

## 3. The trap: do not concatenate scope into the BM25 document

Measured on the current index: the document string (title, common title, aspect, and the three
classification levels) has a **median of 29 words**, p10 20, p90 44. A BIS clause-1 scope runs
50–150 words. Measured across the full run: **median 26 words, p75 48**, so a covered document would
be roughly **2x longer**, and well over that in the tail. Smaller than first feared, but the
asymmetry argument below is unchanged, and coverage is partial by nature.

README section 7 already documents what BM25 length normalisation does to a long document: the DI
pipes miss, where "the alias-bearing document is itself long … BM25 length normalisation then works
against the very document the alias was added to promote." Section 13 names the same thing as an
untried fix: "no field weighting in the keyword index."

Partial coverage makes it worse than a uniform 4x would be. After stage 1, **101 documents are long
and 23,240 are short**. BM25 would then systematically penalise precisely the documents you spent
the effort enriching — and those are the ones already missing. The change could measure *negative*
while the underlying data is good.

---

## 4. Recommended integration: scope text as a third retriever

The pipeline already fuses two ranked lists with reciprocal rank fusion. Add a third.

- **Dense side — put scope text in the embedded text.** This is a clean win and the reason to do
  the work at all: the vector starts describing what the standard covers instead of only what it is
  called. Title + classification + scope is roughly 120 words, well inside `bge-small`'s limit. Keep
  the existing fields; scope is appended, not substituted.
- **Keyword side — a separate BM25 index over scope text alone**, contributing its own ranked list
  to the fusion. Nothing is concatenated, so no document changes length, and the existing
  keyword index and its measured numbers are untouched.
- **Partial coverage handles itself.** A standard with no scope text simply does not appear in the
  third retriever's list. RRF rewards what ranks and ignores what does not, so an uncovered document
  is not penalised — it just has one fewer way to be found. This is the property that makes a third
  retriever right and a boost wrong.

Rebuilding the corpus changes the embedded text, so `index_meta.json` fingerprints will not match.
The stale-vector guard fires and falls back to keyword-only, which silently removes dense retrieval
from every result. **Run the full `01_build_index.py`, not `--no-dense`**, and confirm the warning
is absent before believing any measurement.

---

## 5. Measure on the miss families, not only on the aggregate

README section 8 says the evaluation items are hand-written by someone reading BIS titles, and
section 7 says that biases lexical overlap upward and is why trade names look better than they are.

**The same bias runs the other way for scope text.** Items phrased close to a BIS title are already
found by keyword retrieval; scope text helps most on phrasing that shares no words with the title,
which is exactly what a hand-written set under-represents. Expect the aggregate Recall@5 to move
little, and do not read that as a negative result.

So report two numbers:

1. **Recall@5 on the miss families only.** IS 1367, IS 2556, IS 10124, IS 13730, IS 1554, IS 2062
   are already in `data/eval_set.jsonl` as misses. If scope text is working, they stop missing.
   That is the measurement stage 1 exists to produce.
2. **Aggregate Recall@1/5/10 on all 121**, as a regression guard — the job here is to confirm
   nothing got worse, not to show a headline gain.

IS 458 is a special case: section 8 deliberately keeps it as a documented failure, because the query
says "reinforced cement concrete" and the title says "Precast Concrete Pipes (with and without
Reinforcement)". Its scope paragraph almost certainly contains "reinforced concrete pipe" in full.
If scope text rescues that item, it is the single cleanest demonstration available that the missing
clause 1 was the ceiling — say so in the README rather than quietly deleting the documented failure.

---

## 6. Free bonus: clause 2 gives the graph real edges

`extract` also parses clause 2 into `normative_refs`. These are **authoritative** normative
references, stated by the standard itself.

That matters to the Knowledge Graph workstream. The scraped cross-references in `edges.csv` carry
real noise — a textile standard pointing to a packaged sewage treatment plant — which is why they
are weighted by `same_dept` and `confirmed_both_sides`. Clause 2 has no such problem. An edge that
appears both in `edges.csv` and in clause 2 is confirmed by the document itself.

Hand `normative_refs` to your teammate as a higher-confidence edge source. The parser handles the
BIS reference-table quirk where the left column is a bare number (`1608 : 2005`) rather than a
prefixed one, which a naive `IS\s*\d+` regex misses entirely.

---

## 7. The text is OCR'd, and that needs a gate

BSB Edge scanned these and ran OCR themselves, so we inherit their errors. From the real IS 1786
preview: *"ibis standard ailows"*, *"Meiaiiic mateiial"*, *"Tiik standard AU applies"*,
*"speificed"*, *"mdlcated were vaiid"*.

For retrieval this is survivable, because the words that carry meaning came through intact —
*deformed steel bars*, *reinforcement in concrete*, *Fe415*, *hot-rolled*, *cold-worked*,
*coil form*, *welded*. Those are what has to match "TMT bars Fe500D for RCC work". The garbling
lands mostly on function words. But newer standards will be clean and 1980s scans will not, so
quality varies across the corpus and has to be measured rather than assumed.

**`title_overlap`** is the gate: the share of the title's content words that reappear in the scope.
IS 1786 scores 0.636. A low score means one of three things, all of which you want to catch — bad
OCR, the wrong page came back, or the scope ran into surrounding text. Rows below 0.25 are flagged
`low_title_overlap` rather than `ok`.

```bash
python bis_scope_scraper.py review --out data/scope_text.csv --worst -n 10
```

That prints the lowest-overlap rows first, which is where the failures live. **Decide a cutoff and
exclude rows below it from the index.** A garbled scope adds noise, not signal, and a partially
noisy corpus is harder to reason about than a smaller clean one. Re-running `extract` needs no
network, so tune against the cache freely.

Other statuses to expect: `no_scope_heading` (no preview, or a layout the regex misses),
`too_short`, `too_long`. If `no_scope_heading` dominates, send me one cached page and I will adjust
the patterns.

## 8. Order of work

1. `probe --id 8195` — read one page and confirm it still looks like the IS 1786 example.
2. `fetch --families` — 101 standards, about seven minutes.
3. `extract`, `report`, `review --worst`. Pick a `title_overlap` cutoff.
4. Add scope text to the embedded text; add the third BM25 retriever. Full index rebuild.
5. Measure the six miss families first, then the aggregate as a regression guard.
6. Only if step 5 is positive: `fetch --dept CED ETD MTD`.
7. Hand `normative_refs` to the graph workstream regardless of how step 5 goes.
8. Fold `ics`, `reaffirmed_year` and `committee` back into the dataset — free, and
   `reaffirmed_year` is only 6% filled today.

## What not to do

- **Do not concatenate scope into the existing BM25 document string.** Section 3.
- **Do not turn scope coverage into a boost.** It would reward having been downloaded rather than
  being relevant, and coverage is partial by design.
- **Do not rebuild with `--no-dense` and then measure.** The stale-vector guard will quietly drop
  dense retrieval and you will be comparing hybrid against keyword-only, not before against after.
- **Do not delete the IS 458 documented failure** if scope text fixes it. Record that it was fixed,
  and by what. A failure that later got fixed for a stated reason is stronger evidence than one that
  was never there.