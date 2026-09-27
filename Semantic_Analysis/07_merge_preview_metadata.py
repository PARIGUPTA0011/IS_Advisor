"""Fold reaffirmation years and ICS codes from the BSB Edge previews into standards.csv.

    python Semantic_Analysis/07_merge_preview_metadata.py            # dry run, prints counts
    python Semantic_Analysis/07_merge_preview_metadata.py --write    # writes both files

`bis_scope_scraper.py` reads each standard's preview page, and every page
carries a reaffirmation year and ICS codes whether or not it has usable scope
text. `reaffirmed_year` is only ~5% filled in standards.csv and the knowledge
graph's version checker reads it directly, so this is the cheapest fix available.

Rules, each one measured against the data rather than assumed:

* `wrong_standard` rows are skipped: the page belongs to a different standard,
  so its metadata does too.
* The preview year never overwrites a newer existing year. Where both exist,
  the existing one is newer in about 70% of cases - the preview records the
  reaffirmation current when it was scanned - so the merge takes the maximum.
* A preview year earlier than the edition year is impossible and is dropped.
* `last_confirmed_year` is max(is_year, reaffirmed_year) on every existing row,
  and is recomputed the same way so the two columns cannot disagree.
* `reaffirmed_year_source` records where each year came from, because a
  preview-only year is a lower bound: the standard may have been reaffirmed
  again since.

The same four fields are then copied into standards.jsonl (sync_jsonl), which
the RAG metadata store reads, so the two copies of each record agree.

Idempotent: running it twice gives the same files. Both are tracked in git, so
`git diff IS_Standards_Data/` shows exactly what changed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from is_advisor import config  # noqa: E402


def load_preview_metadata() -> pd.DataFrame:
    scope = pd.read_csv(config.SCOPE_TEXT_CSV, usecols=["kys_id", "scope_status", "reaffirmed_year", "ics"])
    scope = scope[scope["scope_status"] != "wrong_standard"]
    scope["reaffirmed_year"] = pd.to_numeric(scope["reaffirmed_year"], errors="coerce")
    scope["ics"] = scope["ics"].astype("string").str.strip().replace("", pd.NA)
    return scope[["kys_id", "reaffirmed_year", "ics"]].rename(
        columns={"reaffirmed_year": "preview_reaffirmed", "ics": "preview_ics"}
    )


def merge(df: pd.DataFrame, preview: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    # df is read as strings, so every column this does not touch is written back
    # byte for byte - a numeric round trip turns 2024 into 2024.0 and N/A into ''.
    preview = preview.assign(kys_id=preview["kys_id"].astype(str))
    out = df.merge(preview, on="kys_id", how="left")
    year = pd.to_numeric(out["is_year"], errors="coerce")
    old = pd.to_numeric(out["reaffirmed_year"], errors="coerce")
    new = out["preview_reaffirmed"].where(~(out["preview_reaffirmed"] < year))

    stats = {
        "preview year before edition, dropped": int((out["preview_reaffirmed"] < year).sum()),
        "reaffirmed_year newly filled": int((old.isna() & new.notna()).sum()),
        "reaffirmed_year raised": int((old.notna() & (new > old)).sum()),
        "reaffirmed_year kept (existing newer)": int((old.notna() & (new < old)).sum()),
    }

    merged = np.fmax(old, new)
    # Keep a source recorded by an earlier run; otherwise an existing year is KYS's.
    if "reaffirmed_year_source" in out:
        source = out["reaffirmed_year_source"].astype("object")
    else:
        source = pd.Series(np.where(old.notna(), "kys", None), index=out.index, dtype="object")
    from_preview = (old.isna() & new.notna()) | (new > old)
    source = source.where(~from_preview, "bsb_preview")
    out["reaffirmed_year"] = _year_text(merged)
    out["reaffirmed_year_source"] = source.where(merged.notna(), "").fillna("")
    out["last_confirmed_year"] = _year_text(np.fmax(year, merged))

    existing_ics = out["ics"].replace("", pd.NA) if "ics" in out else pd.Series(pd.NA, index=out.index)
    out["ics"] = out["preview_ics"].fillna(existing_ics).fillna("")
    stats["ics filled"] = int((out["ics"] != "").sum())
    stats["reaffirmed_year filled, before"] = int(old.notna().sum())
    stats["reaffirmed_year filled, after"] = int(merged.notna().sum())
    return out.drop(columns=["preview_reaffirmed", "preview_ics"]), stats


def _year_text(values: pd.Series) -> pd.Series:
    return values.map(lambda v: "" if pd.isna(v) else str(int(v)))


JSONL_FIELDS = ("reaffirmed_year", "last_confirmed_year", "reaffirmed_year_source", "ics")


def sync_jsonl(csv_frame: pd.DataFrame, write: bool) -> dict:
    """Copy the merged fields from standards.csv into standards.jsonl.

    The RAG layer's metadata store reads the JSONL, not the CSV, so without
    this the two copies of the same record would silently disagree. Only the
    four fields above change; every other byte of a line is reproduced as it
    was (json.dumps with ensure_ascii=False round-trips the file exactly), key
    order is kept, and the two new keys go at the end of each record.
    """
    path = config.STANDARDS_CSV.with_suffix(".jsonl")
    values = {}
    for row in csv_frame[["kys_id", *JSONL_FIELDS]].itertuples(index=False):
        reaffirmed, confirmed, source, ics = row[1:]
        values[int(row[0])] = {
            "reaffirmed_year": int(reaffirmed) if reaffirmed else None,
            "last_confirmed_year": int(confirmed) if confirmed else None,
            "reaffirmed_year_source": source or None,
            "ics": ics or None,
        }

    raw = path.read_bytes()
    newline = b"\r\n" if b"\r\n" in raw[:200_000] else b"\n"
    out_lines, changed, missing = [], 0, 0
    for line in raw.split(newline):
        if not line.strip():
            out_lines.append(line)
            continue
        record = json.loads(line)
        update = values.get(record["kys_id"])
        if update is None:
            missing += 1
            out_lines.append(line)
            continue
        if any(record.get(k) != v for k, v in update.items()):
            changed += 1
        record.update(update)
        out_lines.append(json.dumps(record, ensure_ascii=False).encode("utf-8"))
    if write:
        path.write_bytes(newline.join(out_lines))
    return {"jsonl records updated": changed, "jsonl records not in csv": missing}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge preview metadata into standards.csv.")
    parser.add_argument("--write", action="store_true", help="write the result (default is a dry run)")
    args = parser.parse_args()

    df = pd.read_csv(config.STANDARDS_CSV, dtype=str, keep_default_na=False)
    out, stats = merge(df, load_preview_metadata())
    for key, value in stats.items():
        print(f"  {key:40s} {value:>7,}")

    assert len(out) == len(df), "merge changed the row count"
    assert list(out.columns[: len(df.columns)]) == list(df.columns), "merge reordered columns"

    for key, value in sync_jsonl(out, write=args.write).items():
        print(f"  {key:40s} {value:>7,}")

    if not args.write:
        print("\nDry run. Re-run with --write to update standards.csv and standards.jsonl.")
        return 0
    # The committed file uses LF; pandas on Windows would otherwise write CRLF
    # and turn every line into a diff.
    out.to_csv(config.STANDARDS_CSV, index=False, lineterminator="\n")
    print(f"Wrote {config.STANDARDS_CSV} and {config.STANDARDS_CSV.with_suffix('.jsonl').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
