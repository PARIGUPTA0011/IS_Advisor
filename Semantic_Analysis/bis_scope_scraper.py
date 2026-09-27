#!/usr/bin/env python3
"""
IS-Advisor :: BIS scope text + normative references, from the BSB Edge preview
==============================================================================

Fills the gap README section 13 calls the quality ceiling: clause 1 (SCOPE) and
clause 2 (REFERENCES) are not in standards.csv.

Source is the free BSB Edge preview page, NOT the PDF. That was the original plan
and it was wrong: the PDF needs an account, arrives watermarked, and is gated
behind an ASP.NET __doPostBack. The preview needs no login at all and carries the
same two clauses as HTML, plus ICS codes and a reaffirmation year.

Two requests per standard, because the preview id cannot be constructed:

  1. GET search_redirect.aspx?id=<kys_id>
       302 -> BIS_SearchStandard.aspx?Standard_Number=IS+1554+:+Part+1&id=7807
  2. that page contains  BIS_Preview.aspx?id=1554_1_1988_reff2020
       <number>_<part>_<year>_reff<year>, and the reaffirmation year is not in
       our data, so step 1 cannot be skipped
  3. GET that preview -> clause 1 and clause 2 as text

The preview is per-part (1554_1 and 1554_2 are different pages), which is what
makes it useful: six of the misses in README section 7 are a query naming the
family where the index holds a dozen near-identical part titles.

WHAT YOU GET BACK IS OCR'd BY BSB EDGE, and older scans are rough - "Meiaiiic
mateiial" for "Metallic material". Content words survive, which is what retrieval
needs, but `title_overlap` is reported per row so bad pages can be found and
dropped. Read section 7 of SCOPE_TEXT.md before indexing any of it.

Usage
-----
  pip install requests

  python bis_scope_scraper.py probe  --id 8195           # inspect one search page
  python bis_scope_scraper.py fetch  --families          # 101 standards, ~7 min
  python bis_scope_scraper.py extract --out data/scope_text.csv
  python bis_scope_scraper.py report  --out data/scope_text.csv
  python bis_scope_scraper.py review  --out data/scope_text.csv -n 10

  python bis_scope_scraper.py fetch --dept CED ETD MTD   # 5,481, several hours

Pages cache to ./cache_preview/<kys_id>.html and are never re-fetched. Extraction
is offline, so re-run it freely while tuning.
"""
import argparse
import csv
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import pandas as pd

CACHE = Path("cache_preview")
STATUS = CACHE / "_status.json"
SEARCH = "https://standardsbis.bsbedge.com/search_redirect.aspx?id={}"
PREVIEW = "https://standardsbis.bsbedge.com/{}"
STANDARDS_CSV = Path("../IS_Standards_Data/standards.csv")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "IS-Advisor-SIH-student-project/0.2 (contact: your-email@example.com)")

MISS_FAMILIES = ["IS 1367", "IS 2556", "IS 10124", "IS 13730", "IS 1554",
                 "IS 2062", "IS 458", "IS 8329", "IS 7098"]
PREVIEW_LINK = re.compile(r"""BIS_Preview\.aspx\?id=([^"'&\s>]+)""", re.I)


# --------------------------------------------------------------------- selection
def load_index(path=None):
    p = Path(path or STANDARDS_CSV)
    if not p.exists():
        sys.exit(f"standards.csv not found at {p} - pass --standards")
    s = pd.read_csv(p, low_memory=False)
    cur = s[(s.status == "current") & s.is_canonical]
    return cur.sort_values(["is_year", "kys_id"]).groupby("is_base_id").tail(1)


def select(df, a):
    if getattr(a, "ids", None):
        return df[df.kys_id.isin([int(i) for i in a.ids])]
    if getattr(a, "families", False):
        pat = "|".join(rf"^{re.escape(f)}( |\(|$)" for f in MISS_FAMILIES)
        return df[df.is_base_id.fillna("").str.match(pat)]
    if getattr(a, "dept", None):
        df = df[df.dept_code.isin([d.upper() for d in a.dept])]
    return df


# --------------------------------------------------------------------- fetch
def session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def read_status():
    return json.loads(STATUS.read_text()) if STATUS.exists() else {}


def fetch_preview(sess, kid, timeout=45):
    """(status, html|None, preview_id|None). Step 1 finds the id, step 2 gets the page."""
    import requests
    try:
        r = sess.get(SEARCH.format(kid), timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return f"error:{type(e).__name__}", None, None
    if r.status_code != 200:
        return f"search_http_{r.status_code}", None, None
    m = PREVIEW_LINK.search(r.text)
    if not m:
        return "no_preview_link", None, None
    pid = unescape(m.group(1))
    try:
        p = sess.get(PREVIEW.format(f"BIS_Preview.aspx?id={pid}"), timeout=timeout)
    except requests.RequestException as e:
        return f"error:{type(e).__name__}", None, pid
    if p.status_code != 200:
        return f"preview_http_{p.status_code}", None, pid
    if len(p.content) < 1500:
        return "preview_empty", None, pid
    return "ok", p.text, pid


def cmd_fetch(a):
    CACHE.mkdir(exist_ok=True)
    df = select(load_index(a.standards), a)
    if df.empty:
        sys.exit("selection is empty")
    status = read_status()
    todo = [int(k) for k in df.kys_id
            if not (CACHE / f"{int(k)}.html").exists()
            and not str(status.get(str(int(k)), "")).startswith(("no_preview", "preview_empty"))]
    print(f"selected {len(df)}, cached {len(df) - len(todo)}, to fetch {len(todo)}")
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        return
    print(f"two requests each at {a.delay}s apart: about "
          f"{len(todo) * a.delay * 2 / 60:.0f} min. Ctrl-C is safe.\n")
    sess, counts = session(), {}
    for n, kid in enumerate(todo, 1):
        st, html, pid = fetch_preview(sess, kid)
        counts[st] = counts.get(st, 0) + 1
        if st == "ok":
            (CACHE / f"{kid}.html").write_text(html, encoding="utf-8")
            status[str(kid)] = pid
        else:
            status[str(kid)] = st
        if n % 10 == 0 or n == len(todo):
            STATUS.write_text(json.dumps(status, indent=0, sort_keys=True))
            print(f"  {n}/{len(todo)}  {counts}", flush=True)
        time.sleep(a.delay * 2)
    STATUS.write_text(json.dumps(status, indent=0, sort_keys=True))
    print(f"\ndone: {counts}")


def cmd_probe(a):
    sess = session()
    kid = a.id or 8195
    r = sess.get(SEARCH.format(kid), timeout=45, allow_redirects=True)
    print(f"search page: HTTP {r.status_code}  {len(r.content):,} bytes\n  {r.url}")
    m = PREVIEW_LINK.search(r.text)
    if not m:
        Path("probe_search.html").write_bytes(r.content)
        sys.exit("  no BIS_Preview link found - saved probe_search.html")
    pid = unescape(m.group(1))
    print(f"  preview id: {pid}")
    p = sess.get(PREVIEW.format(f"BIS_Preview.aspx?id={pid}"), timeout=45)
    Path("probe_preview.html").write_bytes(p.content)
    print(f"preview page: HTTP {p.status_code}  {len(p.content):,} bytes")
    print(f"  saved to {Path('probe_preview.html').resolve()}\n")
    t = html_to_text(p.text)
    print(t[:1200])


# --------------------------------------------------------------------- parsing
def html_to_text(h):
    h = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", h, flags=re.S | re.I)
    h = re.sub(r"<br\s*/?>|</(p|div|tr|li|h\d|td)\s*>", "\n", h, flags=re.I)
    h = re.sub(r"<[^>]+>", " ", h)
    h = unescape(h).replace("\xa0", " ")
    h = MOJI.sub(" ", h)          # scrape damage; the original character is gone
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in h.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# Headings are NOT anchored to line boundaries. The preview often runs the heading
# and its body together on one line, which is what broke the first version.
SCOPE_H = re.compile(r"(?:^|\n|\s)1\s*[.\)]?\s*SCOPE\b", re.I)
REFS_H = re.compile(r"(?:^|\n|\s)2\s*[.\)]?\s*(?:NORMATIVE\s+)?REFERENCE(?:S|D\s+DOCUMENTS?)?\b", re.I)
NEXT_H = re.compile(r"(?:^|\n|\s)3\s*[.\)]?\s*[A-Z][A-Za-z]{3,}")
# Fallback when no heading matches: BIS clause 1 almost always opens this way.
OPENER = re.compile(r"\bThis\s+(?:Indian\s+)?standard\s+"
                    r"(?:covers|prescribes|specifies|lays\s+down|describes|deals\s+with|"
                    r"gives|establishes|provides)\b", re.I)
FOREWORD = re.compile(r"\bFOREWORD\b", re.I)
ICS_RE = re.compile(r"\bICS\s*[:\s]\s*([\d]{2}\.[\d.;\s]*\d)", re.I)
# Pre-2000 standards classify with UDC, not ICS. Different scheme, own column.
UDC_RE = re.compile(r"\bUDC\s*[:\s]\s*([\d][\d./:;\s'()-]*\d)", re.I)
# An adopted IEC/ISO standard's preview shows only the National Foreword; the
# scope lives in the international text it incorporates. Worth its own status.
NATFW = re.compile(r"\bNational\s+Foreword\b", re.I)
# The preview prints its own IS number in the first title line. search_redirect
# sometimes lands on a DIFFERENT standard - IS 13730 Part 47 returned an LPG
# rubber hose - so the page must be checked against what was asked for.
PAGE_ISNO = re.compile(r"\bIS\s*(\d{1,5})\s*(?::\s*Part\s*([\w.]+))?"
                       r"\s*(?::\s*Sec(?:tion)?\s*([\w.]+))?\s*:\s*(?:19|20)\d\d", re.I)
MOJI = re.compile(r"\uFFFD|\u00EF\u00BF\u00BD|ï¿½")
COMM_RE = re.compile(r"\b([A-Z]{2,4})\s*(\d{1,3})\b(?!\d)")
REAFF_RE = re.compile(r"Reaffirmed\s*[:\-]?\s*(\d{4})", re.I)
# Reference entries come in two shapes, and a bare number with neither is the
# wrapped year of the line above. Two passes, no bare numbers.
REF_YEAR = re.compile(r"\b(\d{2,5})\s*(\(\s*Parts?\s*[^)]{1,24}\))?\s*:\s*(\d{4})\b")
REF_PART = re.compile(r"\b(\d{2,5})\s*(\(\s*Parts?\s*[^)]{1,24}\))")
DEPTS = {"AYD", "CED", "CHD", "EED", "ETD", "FAD", "LITD", "MED", "MHD", "MSD",
         "MTD", "PCD", "PGD", "SSD", "TED", "TXD", "WRD"}
STOP = set("this that standard shall with from which the and for are any all its "
           "other than such when where been have has was were will may can".split())


def content_words(t):
    return {w for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in STOP}


_SEG = None


def unjoin(text):
    """BSB Edge drops the space at line ends: 'requirements forsizes',
    'vitreouslaboratory sinks'. Split only long all-lowercase tokens, so
    technical strings and real long words are left alone."""
    global _SEG
    if _SEG is None:
        try:
            import wordsegment
            wordsegment.load()
            _SEG = wordsegment
        except Exception:
            _SEG = False
    if not _SEG:
        return text

    def fix(m):
        w = m.group(0)
        parts = _SEG.segment(w)
        # Accept only a clean two-or-three word split into real-looking pieces.
        if 2 <= len(parts) <= 3 and all(len(p) >= 2 for p in parts) \
                and "".join(parts) == w:
            return " ".join(parts)
        return w
    return re.sub(r"\b[a-z]{8,}\b", fix, text)


def norm_isno(txt):
    """('13730', '47', None) from either an is_base_id or a preview title line."""
    m = re.match(r"\s*IS\s*(\d{1,5})", str(txt) or "", re.I)
    if not m:
        return None
    part = re.search(r"Part\s*[:\s]?\s*([\w.]+)", str(txt), re.I)
    sec = re.search(r"Sec(?:tion)?\s*[:\s]?\s*([\w.]+)", str(txt), re.I)
    return (m.group(1),
            part.group(1).lower() if part else None,
            sec.group(1).lower() if sec else None)


def parse_preview(html, title="", split_joined=False, expect_base_id=""):
    t = html_to_text(html)
    if split_joined:
        t = unjoin(t)
    out = {"scope_text": "", "scope_words": 0, "scope_status": "", "found_by": "heading",
           "udc": "", "page_is_number": "",
           "normative_refs": "", "n_refs": 0, "ics": "", "committee": "",
           "reaffirmed_year": "", "title_overlap": 0.0}

    # Which standard is this page actually about?
    mp = PAGE_ISNO.search(t)
    if mp:
        part = f" (Part {mp.group(2)})" if mp.group(2) else ""
        sec = f" (Sec {mp.group(3)})" if mp.group(3) else ""
        out["page_is_number"] = f"IS {mp.group(1)}{part}{sec}"
    if expect_base_id and out.get("page_is_number"):
        want, got = norm_isno(expect_base_id), norm_isno(out["page_is_number"])
        if want and got and want != got:
            out["scope_status"] = "wrong_standard"
            return out

    m = ICS_RE.search(t)
    if m:
        out["ics"] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(";")
    mu = UDC_RE.search(t)
    if mu:
        out["udc"] = re.sub(r"\s+", " ", mu.group(1)).strip().rstrip(";:")
    anchor = m or mu
    if anchor:
        tail = t[anchor.end():anchor.end() + 80]
        c = COMM_RE.search(tail)
        if c and c.group(1) in DEPTS:
            out["committee"] = f"{c.group(1)} {c.group(2)}"
    m = REAFF_RE.search(t)
    if m:
        out["reaffirmed_year"] = m.group(1)

    # Look for the scope heading after the foreword, since a contents page can
    # mention "1 SCOPE" earlier. Fall back to the standard BIS opening phrase.
    fw = FOREWORD.search(t)
    ms = SCOPE_H.search(t, fw.end() if fw else 0) or SCOPE_H.search(t)
    if ms:
        body = t[ms.end():]
    else:
        mo = OPENER.search(t, fw.end() if fw else 0) or OPENER.search(t)
        if not mo:
            out["scope_status"] = ("foreword_only" if NATFW.search(t)
                                   else "no_scope_heading")
            return out
        body = t[mo.start():]
        out["found_by"] = "opener"
    mr = REFS_H.search(body)
    refs_block = ""
    if mr:
        scope = body[:mr.start()]
        after = body[mr.end():]
        mn = NEXT_H.search(after)
        refs_block = after[:mn.start()] if mn else after[:8000]
    else:
        mn = NEXT_H.search(body)
        scope = body[:mn.start()] if mn else body[:6000]

    scope = re.sub(r"\s*\n\s*", " ", scope)
    scope = re.sub(r"\s{2,}", " ", scope).strip()
    out["scope_text"] = scope
    out["scope_words"] = len(scope.split())

    if refs_block:
        seen = []
        for num, part, _yr in REF_YEAR.findall(refs_block):
            p = re.sub(r"\s+", " ", (part or "")).strip("() ")
            r = f"IS {num}" + (f" ({p.title()})" if p else "")
            if r not in seen:
                seen.append(r)
        for num, part in REF_PART.findall(refs_block):
            p = re.sub(r"\s+", " ", (part or "")).strip("() ")
            r = f"IS {num} ({p.title()})"
            if r not in seen:
                seen.append(r)
        out["normative_refs"] = "; ".join(seen)
        out["n_refs"] = len(seen)

    # QA: a healthy scope repeats the title's own words. Low overlap means the
    # OCR is bad, the wrong page came back, or the scope ran into other text.
    tw, sw = content_words(title), content_words(scope)
    out["title_overlap"] = round(len(tw & sw) / len(tw), 3) if tw else 0.0

    if out["scope_words"] < 12:
        out["scope_status"] = "too_short"
    elif out["scope_words"] > 600:
        out["scope_status"] = "too_long"
        out["scope_text"] = " ".join(scope.split()[:600])
    elif out["title_overlap"] < 0.25:
        out["scope_status"] = "low_title_overlap"
    else:
        out["scope_status"] = "ok"
    return out


def cmd_extract(a):
    files = sorted(CACHE.glob("*.html"), key=lambda p: int(p.stem))
    if a.ids:
        want = {int(i) for i in a.ids}
        files = [f for f in files if int(f.stem) in want]
    if not files:
        sys.exit(f"nothing in {CACHE}/ - run fetch first")
    idx = load_index(a.standards).set_index("kys_id")
    rows = []
    for n, f in enumerate(files, 1):
        kid = int(f.stem)
        isno = idx.at[kid, "is_number"] if kid in idx.index else ""
        title = idx.at[kid, "title_clean"] if kid in idx.index else ""
        base = idx.at[kid, "is_base_id"] if kid in idx.index else ""
        rec = {"kys_id": kid, "is_number": isno}
        try:
            rec.update(parse_preview(f.read_text(encoding="utf-8", errors="replace"),
                                     str(title), split_joined=a.split_joined,
                                     expect_base_id=str(base)))
        except Exception as e:
            rec["scope_status"] = f"error:{type(e).__name__}"
        rows.append(rec)
        if n % 50 == 0 or n == len(files):
            print(f"  {n}/{len(files)}", flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["kys_id", "is_number", "scope_status", "scope_words", "title_overlap",
            "scope_text", "n_refs", "normative_refs", "ics", "committee",
            "reaffirmed_year", "udc", "page_is_number", "found_by"]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r.get("scope_status") == "ok")
    print(f"\n{len(rows)} pages -> {ok} usable scopes ({ok / len(rows):.0%}) -> {out}")
    print(f"now: report --out {out}   and read some with: review --out {out}")


# --------------------------------------------------------------------- QA
def cmd_report(a):
    df = pd.read_csv(a.out)
    print(f"{len(df)} preview pages parsed\n")
    print("scope_status:")
    for k, v in df.scope_status.value_counts().items():
        note = ""
        if k == "foreword_only":
            note = "  <- adopted IEC/ISO text; scope is not on the preview"
        elif k == "wrong_standard":
            note = "  <- search_redirect landed on a different standard; dropped"
        print(f"  {k:18} {v:>5}  {v / len(df):>6.1%}{note}")
    if "found_by" in df.columns:
        print(f"\nfound via: {dict(df.found_by.value_counts())}")
    ok = df[df.scope_status == "ok"]
    if len(ok):
        q = ok.scope_words.quantile([.1, .5, .9]).round().astype(int).tolist()
        print(f"\nscope words p10/p50/p90: {q[0]} / {q[1]} / {q[2]}")
        print(f"title_overlap median: {ok.title_overlap.median():.2f}  "
              f"(low values mean bad OCR or the wrong page)")
        have = lambda c: int(df[c].notna().sum()) if c in df.columns else 0
        print(f"\nbonus fields: ICS on {have('ics')}, UDC on {have('udc')}, "
              f"reaffirmation year on {have('reaffirmed_year')}, "
              f"committee on {have('committee')}")
        print(f"normative references extracted: {int(df.n_refs.sum())}")
        print(f"\nIndexed documents today are a median of 29 words. These scopes are "
              f"{q[1]} words,\nso a covered document would be ~{(29 + q[1]) / 29:.1f}x "
              f"longer if concatenated.\nDo not concatenate - SCOPE_TEXT.md section 3.")


def cmd_review(a):
    df = pd.read_csv(a.out)
    if a.status:
        df = df[df.scope_status == a.status]
    if a.worst:
        df = df.nsmallest(a.n, "title_overlap")
    elif len(df):
        df = df.sample(min(a.n, len(df)), random_state=a.seed)
    if not len(df):
        sys.exit("nothing matches")
    for _, r in df.iterrows():
        print("=" * 78)
        print(f"{r.is_number}  [{r.scope_status}]  {r.scope_words}w  "
              f"overlap {r.title_overlap}  ICS {r.ics}  reaff {r.reaffirmed_year}")
        print(str(r.scope_text)[:800])
        if isinstance(r.normative_refs, str) and r.normative_refs:
            print(f"\n  refs ({r.n_refs}): {r.normative_refs[:250]}")
        print()
    print("`--worst` shows the lowest title_overlap first - that is where bad OCR")
    print("and wrong-page fetches turn up. Re-running extract needs no network.")


def cmd_dump(a):
    """Print the text a cached page actually produces, so parsing can be debugged."""
    f = CACHE / f"{a.id}.html"
    if not f.exists():
        sys.exit(f"{f} not cached")
    t = html_to_text(f.read_text(encoding="utf-8", errors="replace"))
    print(f"{len(t):,} chars, {t.count(chr(10)) + 1} lines\n" + "=" * 70)
    if a.around:
        for m in re.finditer(re.escape(a.around), t, re.I):
            print(f"\n--- at {m.start()} ---\n{t[max(0, m.start() - 200):m.start() + 500]}")
    else:
        print(t[a.skip:a.skip + a.chars])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("probe")
    b.add_argument("--id", type=int)

    f = sub.add_parser("fetch")
    f.add_argument("--standards")
    f.add_argument("--ids", nargs="+")
    f.add_argument("--families", action="store_true",
                   help="the 101 standards behind every miss in README section 7")
    f.add_argument("--dept", nargs="+")
    f.add_argument("--limit", type=int)
    f.add_argument("--delay", type=float, default=2.0)

    e = sub.add_parser("extract")
    e.add_argument("--standards")
    e.add_argument("--ids", nargs="+")
    e.add_argument("--out", default="data/scope_text.csv")
    e.add_argument("--split-joined", action="store_true",
                   help="repair run-together words; needs `pip install wordsegment`")

    d = sub.add_parser("dump")
    d.add_argument("--id", type=int, required=True)
    d.add_argument("--chars", type=int, default=2500)
    d.add_argument("--skip", type=int, default=0)
    d.add_argument("--around", help="print context around this text instead")

    r = sub.add_parser("report")
    r.add_argument("--out", default="data/scope_text.csv")

    v = sub.add_parser("review")
    v.add_argument("--out", default="data/scope_text.csv")
    v.add_argument("-n", type=int, default=5)
    v.add_argument("--status")
    v.add_argument("--worst", action="store_true", help="lowest title_overlap first")
    v.add_argument("--seed", type=int, default=0)

    a = ap.parse_args()
    {"probe": cmd_probe, "fetch": cmd_fetch, "extract": cmd_extract,
     "report": cmd_report, "review": cmd_review, "dump": cmd_dump}[a.cmd](a)


if __name__ == "__main__":
    main()