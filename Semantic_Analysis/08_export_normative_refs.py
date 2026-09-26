"""Export clause 2 normative references as an edge list for the knowledge graph.

    python Semantic_Analysis/08_export_normative_refs.py

Writes data/normative_refs_edges.csv with the same columns as
IS_Standards_Data/edges.csv, so the graph's reference loader can read it by
changing only the file path, plus provenance columns at the end.

These references are stated by the standard itself in clause 2, so unlike the
scraped cross-references they carry no cross-department noise. An edge found in
both files is confirmed by the document. See data/SCOPE_TEXT.md section 6.

Resolution rules:

* `IS 1608`, `IS 1501 (Part 1)`, `IS 2500 (Part 1/Sec 2)` resolve to an
  `is_base_id`. Clause 2 references are undated, and an undated reference means
  the latest edition, so the cited kys_id is the latest canonical edition -
  current if one exists, withdrawn otherwise.
* A bare number that exists only as parts (`IS 2062` after the split) and
  ranges such as `(Parts 1 To 4)` are kept with an empty `cited_id` and the
  reason in `resolution`, rather than guessed.
* `wrong_standard` preview rows are skipped: the page belongs to another standard.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from is_advisor import config, corpus  # noqa: E402

OUT = config.WORK_DIR / "data" / "normative_refs_edges.csv"

EDGE_COLUMNS = [
    "citing_id", "citing_is", "citing_dept", "cited_id", "cited_is", "cited_title", "cited_dept",
    "cited_aspect", "cited_status", "cited_replaced_by_id", "cited_replaced_by_is", "same_dept",
    "confirmed_both_sides",
]

_REF_RE = re.compile(
    r"^IS\s+(?P<num>\d+)"
    r"(?:\s*\(\s*Part\s*(?P<part>\d+)\s*(?:/\s*Sec\s*(?P<sec>\d+)\s*)?\))?$",
    re.IGNORECASE,
)


def to_base_id(ref: str) -> str | None:
    """'IS 2500 (Part 1/Sec 2)' -> 'IS 2500 (Part 1) (Sec 2)'; None if not a single standard."""
    m = _REF_RE.match(ref.strip())
    if not m:
        return None
    base = f"IS {m['num']}"
    if m["part"]:
        base += f" (Part {m['part']})"
    if m["sec"]:
        base += f" (Sec {m['sec']})"
    return base


def latest_by_base(df: pd.DataFrame) -> pd.DataFrame:
    """One row per is_base_id: latest canonical edition, current preferred."""
    canon = df[df["is_canonical"]].copy()
    canon["_current"] = canon["status"].eq("current")
    canon["_year"] = pd.to_numeric(canon["is_year"], errors="coerce").fillna(-1)
    canon = canon.sort_values(["_current", "_year", "kys_id"])
    return canon.groupby("is_base_id").tail(1).set_index("is_base_id")


def main() -> int:
    df = corpus.load_standards()
    by_kys = df.set_index("kys_id")
    latest = latest_by_base(df)
    bases = set(latest.index)

    scope = pd.read_csv(config.SCOPE_TEXT_CSV, usecols=["kys_id", "scope_status", "normative_refs"])
    scope = scope[(scope["scope_status"] != "wrong_standard") & scope["normative_refs"].notna()]

    # Existing scraped edges, compared at base-id level on both sides so an edge
    # recorded against another edition of the same standard still counts.
    edges = pd.read_csv(config.EDGES_CSV, usecols=["citing_id", "cited_id"])
    base_of = df.set_index("kys_id")["is_base_id"]
    scraped = set(zip(edges["citing_id"].map(base_of), edges["cited_id"].map(base_of)))

    rows = []
    for citing_id, status, refs in scope.itertuples(index=False):
        if citing_id not in by_kys.index:
            continue
        citing = by_kys.loc[citing_id]
        seen = set()
        for ref in (r.strip() for r in refs.split(";")):
            if not ref or ref in seen:
                continue
            seen.add(ref)
            row = {c: None for c in EDGE_COLUMNS}
            row.update(citing_id=int(citing_id), citing_is=citing["is_number"],
                       citing_dept=citing["dept_code"], cited_as=ref,
                       citing_scope_status=status, source="clause2_normative")
            base = to_base_id(ref)
            if base is None:
                row["resolution"] = "unparsed (range, list or OCR damage)"
            elif base in bases:
                cited = latest.loc[base]
                row.update(
                    cited_id=int(cited["kys_id"]), cited_is=cited["is_number"],
                    cited_title=cited["title_clean"], cited_dept=cited["dept_code"],
                    cited_aspect=cited["aspect"], cited_status=cited["status"],
                    cited_replaced_by_id=cited["replaced_by_id"],
                    cited_replaced_by_is=cited["replaced_by_is"],
                    same_dept=int(cited["dept_code"] == citing["dept_code"]),
                    in_edges_csv=int((citing["is_base_id"], base) in scraped),
                    resolution="latest edition",
                )
                # confirmed_both_sides is left empty: in edges.csv it means "seen
                # from both standards' KYS pages", which does not apply here.
                # in_edges_csv is the confirmation signal for this file.
            elif any(b.startswith(base + " (") for b in bases):
                row["resolution"] = "family only exists as parts"
            else:
                row["resolution"] = "no such standard in the dataset"
            rows.append(row)

    out = pd.DataFrame(rows)
    extra = ["cited_as", "resolution", "in_edges_csv", "citing_scope_status", "source"]
    out = out[EDGE_COLUMNS + extra]
    for col in ("cited_id", "cited_replaced_by_id", "same_dept", "confirmed_both_sides", "in_edges_csv"):
        out[col] = out[col].astype("Int64")
    out.to_csv(OUT, index=False, lineterminator="\n")

    resolved = out["cited_id"].notna()
    print(f"{len(out):,} references from {out['citing_id'].nunique():,} standards -> {OUT.name}")
    print(out["resolution"].value_counts().to_string())
    print(f"\nresolved: {resolved.sum():,}")
    print(f"  already in edges.csv:   {int(out.loc[resolved, 'in_edges_csv'].sum()):,}")
    print(f"  new edges:              {int((out.loc[resolved, 'in_edges_csv'] == 0).sum()):,}")
    print(f"  same department:        {int(out.loc[resolved, 'same_dept'].sum()):,}")
    print(f"  cited is withdrawn:     {int((out.loc[resolved, 'cited_status'] == 'withdrawn').sum()):,}")
    print(f"  from scope_status ok:   {int((out.loc[resolved, 'citing_scope_status'] == 'ok').sum()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
