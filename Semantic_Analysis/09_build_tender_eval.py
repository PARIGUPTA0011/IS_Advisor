"""Build an evaluation set from real tender documents.

    python Semantic_Analysis/09_build_tender_eval.py              # build data/eval_tenders.jsonl
    python Semantic_Analysis/09_build_tender_eval.py --review     # print every kept item

The hand-written data/eval_set.jsonl was authored by someone reading BIS titles,
which biases lexical overlap upward (README section 8). This set is built from
real bills of quantities instead: an engineer wrote "Providing and fixing ...
conforming to IS 15622", so the item text is the procurement officer's own
wording and the cited standard is the gold answer.

Pipeline, each step there because the raw text needed it:

1. Download every URL in data/tender_sources.txt into cache_tenders/, 2 s apart,
   never fetching a cached file twice.
2. Find every IS citation. Take the item it belongs to: back to the nearest item
   opener ("Providing", "Supplying", "S/F", ...), forward to the next opener or
   sentence end. Merge citations that land in the same item, so an item citing
   a pipe and its gasket is one item with both as gold, not two partial ones.
3. Resolve each citation against the built index: a current standard as is, a
   bare number that BIS later split into parts to all its parts, a withdrawn one
   to its replacement. Items with no resolvable citation are dropped.
4. Remove the citations from the text (the eval measures description -> standard,
   as for the hand-written set), then reject the item if any gold number still
   appears in it.
5. Strip rate/quantity/SOR-code residue, drop fragments and GeM category
   listings, deduplicate, and cap items per gold standard so one schedule of
   rates repeated across tenders cannot dominate.
6. Drop the items listed in REJECTED after manual review, with the reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from is_advisor import config  # noqa: E402

SOURCES = config.WORK_DIR / "data" / "tender_sources.txt"
CACHE = config.WORK_DIR / "cache_tenders"
OUT = config.WORK_DIR / "data" / "eval_tenders.jsonl"
# Put a real contact address here before a large run, as bis_scope_scraper.py asks.
UA = "IS-Advisor-SIH-student-project/0.2 (contact: your-email@example.com)"

MAX_PER_GOLD = 2          # items per gold standard
MIN_WORDS, MAX_WORDS = 8, 130

# Filled in after reading every item the automatic steps keep (--review). Key is
# the item's stable id; the value says why it was removed. The rule behind
# "constituent" rejections: the citation must cover what the line procures, not
# a material or process inside it - "precast drain ... HD wire to IS 432" would
# teach the evaluation that a drain is answered by a wire standard.
_PROSE = "specification prose, not a procurement line"
_LIST = "list of standards, not a procurement line"
_MERGED = "two BOQ items merged by extraction"
_GARBLED = "text garbled by PDF extraction"
_CONSTITUENT = "citation covers a constituent or process, not the item procured"
_DUPLICATE = "near-duplicate of a kept item"
_METHOD = "only citation is a test method for a product item"
REJECTED: dict[str, str] = {
    "t116c74e6": _PROSE, "ted08bd3c": _LIST, "tc44b5bf6": _LIST, "t2310675e": _LIST,
    "tecb85609": _LIST, "t43efe82b": _LIST, "t652f4918": _PROSE, "tcb65a9a3": _PROSE,
    "te8f07a9a": _GARBLED, "t1b6f9573": _MERGED, "te51764d3": _MERGED,
    "te33d80d8": _CONSTITUENT + " (aggregate in concrete)",
    "t465e70a0": _CONSTITUENT + " (aggregate in concrete)",
    "t7addda2e": _CONSTITUENT + " (admixture in concrete)",
    "t50c97929": _CONSTITUENT + " (admixture in concrete)",
    "tcbbae3b8": _CONSTITUENT + " (anodising on tower bolts)",
    "tde426f24": _CONSTITUENT + " (anodising on handles)",
    "t7dd4bc5f": _CONSTITUENT + " (galvanising on grating)",
    "ta0d47b4a": _CONSTITUENT + " (galvanising on grating)",
    "tf2bd6779": _CONSTITUENT + " (HD wire in precast drain)",
    "t81e24ffa": _CONSTITUENT + " (HD wire in precast drain)",
    "tcc4eea94": _CONSTITUENT + " (HD wire in precast cover slab)",
    "td1415695": _DUPLICATE, "taadc9956": _DUPLICATE, "tb494c4f2": _DUPLICATE,
    "t5ae4389f": _DUPLICATE, "t8c90b512": _METHOD + " (pump acceptance tests)",
    # second source round
    "t698f0933": _MERGED, "t53c2ac39": _GARBLED, "t32b2201a": _MERGED,
    "tc09a96f4": _CONSTITUENT + " (galvanising on embedded steel)",
    "t85169a27": _CONSTITUENT + " (road marking paint on precast dividers)",
    "t8d3b7832": _MERGED, "t4d94f58f": _DUPLICATE, "t595811ac": _PROSE, "tffbc297d": _MERGED,
    "tad913f4a": _CONSTITUENT + " (particle board in a table)",
    "t28910dd4": _CONSTITUENT + " (CRCA sheet in a steel cupboard)",
    "t7303638f": _CONSTITUENT + " (CRCA sheet in a steel cupboard)",
    "tb8c91aca": _CONSTITUENT + " (motor in a centrifugal fan)",
    "ta3a6fef0": _LIST,
    # after raising MAX_WORDS to 130
    "t86bf6c9d": _PROSE, "taf36af50": _PROSE, "te843e276": _PROSE, "t68b0759b": _LIST,
    "tbe6a8ccd": _LIST, "tcd4e9733": _LIST, "t8765b4c5": _LIST, "t8f76c3fe": _MERGED,
    "t0e249922": _PROSE, "t0a4bff22": _PROSE, "t1a54b853": _DUPLICATE,
    "t05a6d794": _METHOD + " (LED photometry)",
    # siblings that surfaced once the rejections above stopped taking their slots
    "t03be8981": _CONSTITUENT + " (anodising on door stopper)",
    "t0f01930f": _CONSTITUENT + " (anodising on sliding door bolts)",
    "tc43e90cf": _CONSTITUENT + " (HD wire in precast drain)",
    "t9ddf738a": _CONSTITUENT + " (HD wire in precast drain)",
    "te45e0584": _CONSTITUENT + " (HD wire in precast cover slab)",
    "t1aad5171": _CONSTITUENT + " (galvanising on grating)",
    "tc27924bb": _CONSTITUENT + " (particle board in a table)",
    "ta955d7e3": _DUPLICATE, "t6e3b2f8e": _DUPLICATE, "tdf72585c": _PROSE, "t8cf49ff9": _MERGED,
}

# The same constituent citations recur across a whole BOQ series (every drain
# size, every anodised fitting), so they are rejected by rule rather than by id:
# (the only gold standards cited, phrase showing the citation is for a constituent).
CONSTITUENT_RULES = [
    ({"IS 1868"}, re.compile(r"anodi[sz]ed", re.I), "anodising on hardware"),
    ({"IS 432 (Part 1)", "IS 432 (Part 2)"}, re.compile(r"HD\s*Wire", re.I), "HD wire in precast units"),
    ({"IS 2629 (Part 1)"}, re.compile(r"galvanis", re.I), "galvanising on steelwork"),
    ({"IS 12823"}, re.compile(r"table|workstation", re.I), "particle board in furniture"),
    ({"IS 513 (Part 1)", "IS 513 (Part 2)"}, re.compile(r"CRCA", re.I), "CRCA sheet in furniture"),
]


def constituent_reason(entry: dict) -> str | None:
    for golds, phrase, reason in CONSTITUENT_RULES:
        if set(entry["gold"]) <= golds and phrase.search(entry["text"]):
            return reason
    return None

YEAR = r"(?:\s*[:/\-]\s*(?:19|20)\d{2}(?!\d))?"
CITE = re.compile(
    # Case-sensitive "IS" and no word boundary before it: BOQ text loses its
    # spaces ("conformingto IS:1786andIS13920"), and "this 2000" is not a citation.
    r"(?-i:(?<![A-Z0-9])(?:IS|I\.S\.|BIS))\s*[:\-.]?\s*(\d{2,5})" + YEAR
    + r"(?:\s*[\(\-\s]*(?:Part|Pt\.?)[\s\-:]*([IVX]+|\d+)\)?)?"
    + r"(?:\s*[\(\-\s/]*(?:Sec(?:tion)?\.?)[\s\-:]*(\d+)\)?)?" + YEAR
    # Continuation lists: "IS 4984/ 14151/ 12786" cites four standards.
    + r"((?:\s*/\s*\d{3,5}(?!\d))*)",
    re.IGNORECASE,
)
# Capitalised only: a BOQ item opens with "Providing"; lowercase "supply of" or
# "laying shall" is specification prose, and matching it pulled whole clauses
# and lists of standards in as if they were items.
OPENER = re.compile(
    r"(?<![A-Za-z])(?:Providing|Supplying|Supply|S\s*/\s*F|S\s*&\s*F|SITC|Fabricating|"
    r"Construction of|Constructing|Manufacture|Procurement of|Laying|Filling|Painting|"
    r"Dismantling|Excavation|Earth work)\b"
)
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}

# Residue from BOQ tables: rates, quantities, schedule-of-rates item codes.
_RESIDUE = [
    re.compile(r"\b(?:R\d\s*[-\s]\s*)?[A-Z]{2,4}(?:\s*[-\s]\s*[A-Z0-9]{1,5}){1,4}\s*-\s*\d+\b"),
    re.compile(r"\b(?:Each|Nos?|Sqm|Cum|Rmt|Mtr|MTR|Meter|Metre|Square Meter|quintal|EACH)\b(?:\s+[\d,.]+)+"),
    re.compile(r"(?<![\w.])\d{1,3}(?:,\d{2,3})+(?:\.\d+)?"),         # 6,72,182.75
    re.compile(r"(?<![\w.])\d+\.\d{2}(?![\w%])"),                     # 3272.00
    re.compile(r"\bPH SOR P \d+ I\.No\.?\s*[\d.]+"),
    re.compile(r"\bPage \d+ of \d+"),
    re.compile(r"(?<=\s)\d{1,3}\s+\d{1,2}\.\d{1,3}(?:/\d+)?(?=\s)"),     # item no + SOR ref: "26 9.18"
]
_JUNK = re.compile(r"Searched String|Category not available|GeMARPTS|MPPWD ITEM|RATE AMOUNT", re.I)


def download() -> list[tuple[str, Path]]:
    import requests

    CACHE.mkdir(exist_ok=True)
    urls = [u.strip() for u in SOURCES.read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.startswith("#")]
    out = []
    for url in urls:
        path = CACHE / (hashlib.md5(url.encode()).hexdigest()[:10] + ".pdf")
        if not path.exists():
            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=90)
                if r.ok and r.content[:4] == b"%PDF":
                    path.write_bytes(r.content)
                else:
                    print(f"  ! {r.status_code} {url}")
            except requests.RequestException as exc:
                print(f"  ! {exc.__class__.__name__} {url}")
            time.sleep(2)
        if path.exists():
            out.append((url, path))
    return out


def pdf_text(path: Path) -> str:
    """Extracted text, cached beside the PDF: one 38 MB document takes minutes."""
    cached = path.with_suffix(".txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        text = " ".join((p.extract_text() or "") for p in pdf.pages)
    text = re.sub(r"\(cid:\d+\)", " ", text)
    text = re.sub(r"[^\x00-\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    cached.write_text(text, encoding="utf-8")
    return text


def citations(match: re.Match) -> list[str]:
    """Every base id one citation match names."""
    base = f"IS {int(match.group(1))}"
    if match.group(2):
        part = match.group(2).upper()
        base += f" (Part {ROMAN.get(part, part)})"
    if match.group(3):
        base += f" (Sec {int(match.group(3))})"
    more = [f"IS {int(n)}" for n in re.findall(r"\d{3,5}", match.group(4) or "")]
    return [base] + more


def items_from(text: str):
    """(item text, raw citation spans, cited base ids) for each cited BOQ item."""
    by_start: dict[int, dict] = {}
    for m in CITE.finditer(text):
        openers = [o.start() for o in OPENER.finditer(text, max(0, m.start() - 700), m.start())]
        if not openers:
            continue
        begin = openers[-1]
        entry = by_start.setdefault(begin, {"spans": [], "cited": []})
        entry["spans"].append((m.start(), m.end()))
        entry["cited"].extend(citations(m))
    for begin, entry in by_start.items():
        last = max(e for _, e in entry["spans"])
        nxt = OPENER.search(text, last)
        stop = re.search(r"(?<!\d)\.(?=\s+[A-Z(])", text[last:last + 300])
        end = min(x for x in (
            nxt.start() if nxt else len(text),
            last + stop.start() + 1 if stop else last + 300,
        ))
        yield text[begin:end], [(s - begin, e - begin) for s, e in entry["spans"]], entry["cited"]


def clean(item: str, spans: list[tuple[int, int]]) -> str:
    for s, e in sorted(spans, reverse=True):
        item = item[:s] + " " + item[e:]
    for pattern in _RESIDUE:
        item = pattern.sub(" ", item)
    item = re.sub(r"\b(?:conforming|confirming|comforming|conform)\s+to\s*(?=[,.;)]|$|and\b|with\b)",
                  " ", item, flags=re.I)
    item = re.sub(r"\(\s*[,;&]?\s*\)", " ", item)
    item = re.sub(r"\s+([,.;:])", r"\1", item)
    return re.sub(r"\s+", " ", item).strip(" ,.;:-")


def resolver():
    corpus = pd.read_parquet(config.CORPUS_PARQUET)
    lookup = pd.read_parquet(config.LOOKUP_PARQUET)
    indexed = set(corpus["is_base_id"])
    base_of = dict(zip(lookup["kys_id"], lookup["is_base_id"]))

    def resolve(base: str) -> tuple[list[str], str]:
        if base in indexed:
            return [base], "current"
        parts = sorted(b for b in indexed if b.startswith(base + " ("))
        if parts:
            return parts, "split into parts"
        rows = lookup[lookup["is_base_id"] == base].sort_values("is_year", na_position="first")
        if len(rows):
            replaced = rows.iloc[-1]["replaced_by_id"]
            if pd.notna(replaced) and base_of.get(int(replaced)) in indexed:
                return [base_of[int(replaced)]], "withdrawn, replaced"
        return [], "unresolved"

    return resolve


def build(review: bool) -> list[dict]:
    resolve = resolver()
    raw, stats = [], Counter()
    for url, path in download():
        try:
            text = pdf_text(path)
        except Exception as exc:  # a broken PDF costs one source, not the run
            print(f"  ! unreadable {path.name}: {exc}")
            continue
        for item, spans, cited in items_from(text):
            stats["cited items"] += 1
            if _JUNK.search(item):
                stats["dropped: table/GeM residue"] += 1
                continue
            gold, how = [], []
            for base in dict.fromkeys(cited):
                resolved, reason = resolve(base)
                gold.extend(resolved)
                how.append(f"{base}: {reason}")
            gold = list(dict.fromkeys(gold))
            if not gold:
                stats["dropped: no citation resolves"] += 1
                continue
            text_clean = clean(item, spans)
            numbers = {re.search(r"\d+", g).group() for g in gold} | {re.search(r"\d+", c).group() for c in cited}
            if any(re.search(rf"(?<!\d){n}(?!\d)", text_clean) for n in numbers):
                stats["dropped: cited number still in text"] += 1
                continue
            n_words = len(text_clean.split())
            if not MIN_WORDS <= n_words <= MAX_WORDS:
                stats["dropped: too short or too long"] += 1
                continue
            raw.append({"text": text_clean, "gold": gold, "cited_as": list(dict.fromkeys(cited)),
                        "resolution": how, "source": url, "source_text": item.strip()})

    # Deduplicate on the opening words - the same schedule-of-rates item recurs
    # across tenders with different sizes and quantities appended.
    # Manual rejections are applied first, so a rejected item never takes a
    # duplicate slot or a per-standard slot from an acceptable one.
    seen, per_gold, kept = set(), Counter(), []
    for entry in raw:
        entry["id"] = "t" + hashlib.md5(entry["source_text"].encode()).hexdigest()[:8]
        if entry["id"] in REJECTED:
            stats["dropped: manual review"] += 1
            continue
        if constituent_reason(entry):
            stats["dropped: constituent rule"] += 1
            continue
        key = " ".join(re.findall(r"[a-z]+", entry["text"].lower())[:14])
        if key in seen:
            stats["dropped: duplicate"] += 1
            continue
        seen.add(key)
        primary = entry["gold"][0]
        if per_gold[primary] >= MAX_PER_GOLD:
            stats[f"dropped: over {MAX_PER_GOLD} per gold standard"] += 1
            continue
        per_gold[primary] += 1
        kept.append(entry)

    for key, value in stats.items():
        print(f"  {key:44s} {value:>5}")
    print(f"  {'kept':44s} {len(kept):>5}  from {len({e['source'] for e in kept})} documents")
    if review:
        for e in kept:
            print(f"\n{e['id']}  gold={e['gold'][:4]}{' ...' if len(e['gold']) > 4 else ''}\n  {e['text']}")
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the real-tender evaluation set.")
    parser.add_argument("--review", action="store_true", help="print every kept item for review")
    args = parser.parse_args()
    kept = build(args.review)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        for entry in kept:
            fh.write(json.dumps({"id": entry["id"], "text": entry["text"], "gold": entry["gold"],
                                 "cited_as": entry["cited_as"], "source": entry["source"],
                                 "source_text": entry["source_text"]}, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(kept)} items to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
