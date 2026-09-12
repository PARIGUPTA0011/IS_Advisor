"""Build the retrieval corpus from standards.csv.

Two frames come out of here and they do different jobs (trap 3):

* the **index** - canonical, current, latest-edition rows only (23,341 docs).
  This is what we ever recommend.
* the **lookup** - every row including withdrawn ones, keyed by IS number, so a
  tender citing a dead standard can still be resolved.
"""
from __future__ import annotations

import re
import pandas as pd

from . import config

# "(Third Revision)", "(Superseding IS 1234)" and friends carry no domain signal
# and appear in ~10k titles, so they are stripped before indexing.
_REVISION_RE = re.compile(
    r"\(\s*(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|superseding|reaffirmed)[^)]*\)",
    re.IGNORECASE,
)
# The scrape mangled smart quotes into U+FFFD and backticks; they split tokens.
_JUNK_CHARS_RE = re.compile(r"[�`‘’“”]")
# The scrape turned some en-dashes into '?'; leaving them in splits tokens badly.
_MOJIBAKE_RE = re.compile(r"\s[?]\s")
_WS_RE = re.compile(r"\s+")

_MISSING = {"", "n/a", "na", "none", "nan", "-"}


def clean_text(value) -> str:
    """Normalise one free-text field, returning '' for missing/placeholder values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    if text.strip().lower() in _MISSING:
        return ""
    text = _MOJIBAKE_RE.sub(" - ", text)
    text = _JUNK_CHARS_RE.sub(" ", text)
    text = _REVISION_RE.sub(" ", text)
    text = text.replace("--", " - ")
    text = _WS_RE.sub(" ", text).strip(" -:;,")
    return text


def load_standards() -> pd.DataFrame:
    df = pd.read_csv(config.STANDARDS_CSV, low_memory=False)
    df["is_year"] = pd.to_numeric(df["is_year"], errors="coerce")
    return df


def build_index_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical + current + latest edition per base id (trap 1).

    `status == 'current'` is not the same as 'newest edition' - 540 base ids
    carry more than one current row - so the max `is_year` per `is_base_id`
    decides. Ties fall back to the higher kys_id, which is the later scrape.
    """
    live = df[(df["status"] == "current") & (df["is_canonical"])].copy()
    live["_year_sort"] = live["is_year"].fillna(-1)
    live = live.sort_values(["_year_sort", "kys_id"])
    latest = live.groupby("is_base_id", as_index=False).tail(1).copy()
    return latest.drop(columns=["_year_sort"]).sort_values("kys_id").reset_index(drop=True)


def past_edition_vocabulary(df: pd.DataFrame, index_frame: pd.DataFrame) -> pd.Series:
    """Words used by *earlier* editions of the same standard but not the latest.

    This is alias source #1 from the plan: free, real BIS phrasing, and the
    closest offline stand-in for the missing scope text. Withdrawn editions are
    deliberately included - they are not recommendable, but their wording is
    still evidence of what the standard covers.
    """
    latest_ids = set(index_frame["kys_id"])
    history = df[~df["kys_id"].isin(latest_ids)][["is_base_id", "title_clean", "common_title"]]

    current_words = {
        base: set(_tokens(text))
        for base, text in zip(index_frame["is_base_id"], index_frame["_title_text"])
    }

    extra: dict[str, list[str]] = {}
    for base, title, common in history.itertuples(index=False):
        if base not in current_words:
            continue
        seen = current_words[base]
        bucket = extra.setdefault(base, [])
        for field in (title, common):
            for token in _content_tokens(clean_text(field)):
                if token not in seen and token not in bucket:
                    bucket.append(token)
    return pd.Series({base: " ".join(words) for base, words in extra.items()}, dtype="object")


# Function words and BIS boilerplate. Mined vocabulary is only worth indexing
# when it names something; "for" and "part" appear in every other title.
_VOCAB_STOPWORDS = frozenset("""
and are but for from had has its not the that their them they this was were
with within without into over under per etc such shall may can all any other
others part sec section revision reaffirmed amendment amendments volume
""".split())


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def _content_tokens(text: str) -> list[str]:
    return [t for t in _tokens(text) if t not in _VOCAB_STOPWORDS]


def load_curated_aliases() -> pd.Series:
    """Hand-curated trade names, keyed by is_base_id. Optional file."""
    if not config.CURATED_ALIASES.exists():
        return pd.Series(dtype="object")
    aliases = pd.read_csv(config.CURATED_ALIASES)
    grouped = aliases.groupby("is_base_id")["aliases"].apply(lambda s: " ".join(s.astype(str)))
    return grouped


def build_corpus(use_past_editions: bool = True, use_aliases: bool = True) -> pd.DataFrame:
    """Assemble the document text every retriever reads."""
    df = load_standards()
    index = build_index_frame(df)

    index["_title_text"] = index["title_clean"].map(clean_text)
    index["_common_text"] = index["common_title"].map(clean_text)
    index["_aspect_text"] = index["aspect"].map(clean_text)
    for col in ("group", "sub_group", "sub_sub_group"):
        index[f"_{col}_text"] = index[col].map(clean_text)

    index["_classification"] = [
        " ".join(dict.fromkeys(p for p in parts if p))
        for parts in zip(index["_group_text"], index["_sub_group_text"], index["_sub_sub_group_text"])
    ]

    past = past_edition_vocabulary(df, index) if use_past_editions else pd.Series(dtype="object")
    index["_past_vocab"] = index["is_base_id"].map(past).fillna("") if len(past) else ""

    curated = load_curated_aliases() if use_aliases else pd.Series(dtype="object")
    index["_aliases"] = index["is_base_id"].map(curated).fillna("") if len(curated) else ""

    # Never embed the bare title: "Specification for Bund Former" means nothing
    # on its own, the classification path is what carries the domain.
    index["doc_text"] = [
        _join(title, common, aspect, classification)
        for title, common, aspect, classification in zip(
            index["_title_text"], index["_common_text"], index["_aspect_text"],
            index["_classification"],
        )
    ]
    # Trade names and historic wording go to BM25 only. "TMT bar" is a token to
    # match exactly, and pasting a dozen synonyms into a 20-word title would
    # drag the embedding away from what the standard is actually about.
    index["lexical_text"] = [
        _join(doc, past, aliases, str(number))
        for doc, past, aliases, number in zip(
            index["doc_text"], index["_past_vocab"], index["_aliases"], index["is_number"]
        )
    ]

    keep = [
        "kys_id", "is_number", "is_base_id", "is_year", "title_clean", "common_title",
        "aspect", "group", "sub_group", "sub_sub_group", "dept_code", "committee_code",
        "mandatory_cert", "qco_status", "doc_text", "lexical_text",
    ]
    out = index[keep].copy()
    out["title_display"] = index["_title_text"]
    return out.reset_index(drop=True)


def build_lookup(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every standard, current or withdrawn, for resolving cited IS numbers."""
    if df is None:
        df = load_standards()
    keep = [
        "kys_id", "is_number", "is_base_id", "is_year", "status", "is_canonical",
        "title_clean", "replaced_by_id", "replaced_by_is", "dept_code", "mandatory_cert",
    ]
    out = df[keep].copy()
    out["title_display"] = out["title_clean"].map(clean_text)
    return out.reset_index(drop=True)


def _join(*parts: str) -> str:
    return " | ".join(p for p in (p.strip() for p in parts) if p)
