# Handoff: clause 2 normative references and new standards.csv columns

For the Knowledge Graph workstream. Two things are ready to load: a new edge file, and two
extra columns in `standards.csv`.

## 1. `Semantic_Analysis/data/normative_refs_edges.csv`: 37,602 references

These come from **clause 2 (Normative References) of each standard**, as shown on the BSB Edge
preview page. The standard lists them itself, so this source has none of the cross-department noise
in `edges.csv`: no textile standard pointing at a sewage plant.

**It loads with your existing script.** The first 13 columns are exactly the `edges.csv` columns, in
the same order. Point `04_create_reference_relationships.py.py` at this file and it works unchanged.
Five columns are added at the end:

| Column | Meaning |
|---|---|
| `cited_as` | the reference as printed, e.g. `IS 1501 (Part 1)` |
| `resolution` | how `cited_id` was chosen (below) |
| `in_edges_csv` | 1 if `edges.csv` already has this pair, compared on `is_base_id` for both sides |
| `citing_scope_status` | quality flag from the scrape; `ok` rows are the cleanest |
| `source` | always `clause2_normative` |

| `resolution` | n | `cited_id` |
|---|---|---|
| `latest edition` | 35,896 | filled |
| `family only exists as parts` | 917 | empty: a bare `IS 2062` where only its parts exist |
| `no such standard in the dataset` | 728 | empty |
| `unparsed (range, list or OCR damage)` | 61 | empty |

Of the 35,896 resolved references:

- **24,627 already exist in `edges.csv`.** Those edges are now confirmed by the standard's own text,
  which is a stronger signal than `confirmed_both_sides`. Where `edges.csv` has a pair and this file
  does too, it is safe to trust it regardless of `same_dept`.
- **11,269 are new edges** that `edges.csv` does not have.
- 4,007 point at a withdrawn standard. `cited_replaced_by_id` / `cited_replaced_by_is` are filled
  from `standards.csv`, so your `REPLACED_BY` chain handles them.

**Things to know:**

- **The referenced edition is inferred.** Clause 2 references are undated, and under BIS convention
  an undated reference means the latest edition. So `cited_id` is the latest canonical edition:
  current if one exists, otherwise the latest withdrawn one. Example: `IS 2062` resolves to the
  withdrawn IS 2062:2011, with `cited_replaced_by_is = IS 2062 (Part 1):2025`.
- **`confirmed_both_sides` is deliberately left empty.** In `edges.csv` it means "seen from both
  standards' KYS pages", which does not apply to this source. Use `in_edges_csv` instead.
- **Coverage follows the preview pages.** 7,946 standards list at least one reference. Adopted
  IS/ISO and IS/IEC standards mostly show only a National Foreword and are underrepresented.
- A suggested relationship type is `(:Standard)-[:NORMATIVELY_REFERENCES]->(:Standard)`, alongside
  `REFERENCES`, so the two sources stay distinguishable in queries.

Regenerate with `python Semantic_Analysis/08_export_normative_refs.py`.

## 2. `IS_Standards_Data/standards.csv`: reaffirmation years and ICS codes

Merged by `Semantic_Analysis/07_merge_preview_metadata.py`. No existing values were overwritten
except as stated below, no rows were added or removed, and the existing columns are unchanged.

| | before | after |
|---|---|---|
| `reaffirmed_year` filled | 1,642 | **11,442** |
| `ics` (new column) | n/a | **14,959** |
| `reaffirmed_year_source` (new column) | n/a | `kys` / `bsb_preview` |

- `last_confirmed_year` is recomputed as max(`is_year`, `reaffirmed_year`), which is how it was
  already defined on every row, so your `02_create_graph.py` needs no change.
- **A `bsb_preview` year is a lower bound.** Where both sources had a year, the existing KYS year was
  newer in 1,063 of 1,493 cases: the preview records the reaffirmation current when it was scanned.
  So the merge only ever takes the newer year, and a version check should treat `bsb_preview` as
  "reaffirmed at least this recently", not as the latest confirmation.
- 14 preview years earlier than the edition year were impossible and were dropped.
- `ics` holds semicolon-separated ICS codes, e.g. `55.080; 85.080`.
- `standards.jsonl` carries the same four fields (`reaffirmed_year`, `last_confirmed_year`,
  `reaffirmed_year_source`, `ics`), copied from the CSV by the same script, so the two files agree
  record for record. No other field in either file changed.
