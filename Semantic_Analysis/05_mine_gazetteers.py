"""Mine material, property and environment vocabulary out of the corpus itself.

Hand-written term lists encode the author's vocabulary rather than BIS's, which
is exactly the circularity the README flags for `data/aliases.csv`. These lists
are derived from `title_clean` across the indexed documents instead, so they
match words that are actually in the index and can be regenerated whenever the
dataset changes.

    python Semantic_Analysis/05_mine_gazetteers.py
    python Semantic_Analysis/05_mine_gazetteers.py --min-count 3 --report

Writes one term per line to data/gazetteers/*.txt. Files named `*_manual.txt`
are hand-maintained, never overwritten, and merged in at load time for terms the
corpus cannot supply.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

from is_advisor import config  # noqa: E402
from is_advisor.gazetteer import GAZETTEER_DIR, load_gazetteer  # noqa: E402

# A bigram is only a term if its modifier carries meaning. "stainless steel" is
# a material; "of steel", "part rubber" and "sec glass" are grammar and
# document structure that happen to sit next to a material word.
_MODIFIER_STOPWORDS = frozenset("""
a an the of for and or to in on at by with from as is are be this that these those
its their it into over under per etc such shall may can all any other others
part sec section sub clause table fig figure method methods test tests testing
specification specifications code practice general requirements requirement
determination measurement sampling analysis grade grades type types class classes
size sizes dimension dimensions use used uses application applications system
systems equipment apparatus machine machines plant works work industrial
""".split())

# Seeds are explicit terms, one per entry. Writing them as free text and
# splitting on whitespace silently turned "corrosion resistant" into the two
# useless unigrams "corrosion" and "resistant".
_SEEDS: dict[str, list[str]] = {
    "material": [
        "stainless steel", "mild steel", "carbon steel", "alloy steel", "cast iron",
        "ductile iron", "wrought iron", "pig iron", "galvanized steel",
        "aluminium", "aluminum", "copper", "brass", "bronze", "zinc", "lead", "nickel",
        "titanium", "hdpe", "ldpe", "pvc", "upvc", "ppr", "polyethylene",
        "polypropylene", "polycarbonate", "polyester", "nylon", "rubber", "neoprene",
        "silicone", "bitumen", "asphalt", "cement", "concrete", "mortar", "timber",
        "plywood", "bamboo", "jute", "cotton", "silk", "wool", "glass", "ceramic",
        "porcelain", "vitreous china", "fibreglass", "cast steel",
    ],
    "property": [
        "corrosion resistant", "fire resistant", "fire retardant", "flame retardant",
        "water resistant", "weather resistant", "heat resistant", "chemical resistant",
        "abrasion resistant", "impact resistant", "corrosion resistance",
        "waterproof", "dustproof", "shockproof", "rustproof", "leakproof",
        "galvanized", "insulated", "coated", "reinforced", "tempered", "hardened",
        "anodized", "non toxic", "food grade", "self extinguishing", "shatterproof",
    ],
    "environment": [
        "outdoor", "indoor", "submersible", "underground", "underwater", "overhead",
        "buried", "marine", "coastal", "tropical", "desert", "portable", "stationary",
        "mobile", "hazardous", "explosive", "wall mounted", "floor mounted",
        "pole mounted", "ceiling mounted", "surface mounted", "flush mounted",
        "in situ", "on site",
    ],
}

# A term is kept when its final word is one of these, which is what makes an
# n-gram a material rather than a thing made of one. Deliberately narrow:
# "installation", "service" and "duty" pulled in "computing service" and
# "fabrication installation", which describe no environment at all.
_HEAD_WORDS: dict[str, set[str]] = {
    "material": set("""
    steel iron alloy alloys plastic plastics rubber cement concrete wood timber
    copper brass bronze aluminium aluminum zinc lead nickel glass ceramic
    polymer polymers resin resins
    """.split()),
    "property": set("""
    resistant resistance proof retardant treated coated insulated galvanized
    reinforced tempered hardened anodized plated
    """.split()),
    "environment": set("mounted mounting".split()),
}

# Generic on their own: every second title mentions an alloy or a polymer, so a
# bare head word is only a term when it names a specific material.
_TOO_GENERIC_ALONE = frozenset({
    "alloy", "alloys", "plastic", "plastics", "polymer", "polymers", "resin", "resins",
    "material", "materials", "metal", "metals",
})

# The review pass over the mined candidates. These read like properties but are
# measured electrical or laboratory quantities, so a tender asking for a
# "corrosion resistant" tank must not match a standard about insulation
# resistance testing. "separations proof" is simply a bad parse.
_REVIEWED_OUT = frozenset({
    "electrical resistance", "insulation resistance", "contact resistance",
    "finish resistance", "flex resistance", "grease resistance",
    "hydrolytic resistance", "separations proof", "dip galvanized",
    "dentistry polymer", "copper iron", "iron nickel", "gauge steel",
})


def mine(titles: pd.Series, min_count: int) -> dict[str, set[str]]:
    unigrams: collections.Counter = collections.Counter()
    bigrams: collections.Counter = collections.Counter()
    for title in titles.fillna(""):
        words = re.findall(r"[a-z]+", str(title).lower())
        unigrams.update(words)
        bigrams.update(zip(words, words[1:]))

    mined: dict[str, set[str]] = {}
    for kind, heads in _HEAD_WORDS.items():
        found: set[str] = set()

        # Seeds only survive if the corpus actually uses them.
        for seed in _SEEDS[kind]:
            parts = seed.split()
            if len(parts) == 1 and unigrams.get(parts[0], 0) >= min_count:
                found.add(seed)
            elif len(parts) == 2 and bigrams.get((parts[0], parts[1]), 0) >= min_count:
                found.add(seed)

        for (modifier, head), count in bigrams.items():
            if count < min_count or head not in heads:
                continue
            if modifier in _MODIFIER_STOPWORDS or len(modifier) < 3:
                continue
            found.add(f"{modifier} {head}")

        # A bare head word counts only where it names a specific material.
        if kind == "material":
            for head in heads - _TOO_GENERIC_ALONE:
                if unigrams.get(head, 0) >= min_count:
                    found.add(head)
        mined[kind] = found - _TOO_GENERIC_ALONE - _REVIEWED_OUT
    return mined


def coverage(titles: pd.Series, terms: set[str]) -> float:
    """Share of titles containing any term, which is what bounds a boost built on it."""
    if not terms:
        return 0.0
    pattern = re.compile(
        r"\b(?:" + "|".join(sorted((re.escape(t) for t in terms), key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    return float(titles.fillna("").astype(str).str.contains(pattern).mean())


_NUMERIC_SPEC_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:l|litre|litres|ml|mm|cm|m|kg|g|kw|kva|w|v|a|hz|mpa|bar|dn|nb)\b",
    re.IGNORECASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Mine attribute gazetteers from the corpus.")
    parser.add_argument("--min-count", type=int, default=4, help="minimum corpus frequency")
    parser.add_argument("--report", action="store_true", help="print coverage over indexed titles")
    args = parser.parse_args()

    if not config.CORPUS_PARQUET.exists():
        parser.error(f"no corpus at {config.CORPUS_PARQUET} - run 01_build_index.py first")
    corpus = pd.read_parquet(config.CORPUS_PARQUET)
    titles = corpus["title_display"]
    print(f"Mining from {len(corpus):,} indexed titles (min count {args.min_count})\n")

    GAZETTEER_DIR.mkdir(parents=True, exist_ok=True)
    mined = mine(titles, args.min_count)

    for kind, terms in sorted(mined.items()):
        path = GAZETTEER_DIR / f"{kind}.txt"
        path.write_text(
            "# generated by 05_mine_gazetteers.py - edit "
            f"{kind}_manual.txt instead\n" + "\n".join(sorted(terms)) + "\n",
            encoding="utf-8",
        )
        combined = load_gazetteer(kind)
        manual_only = len(combined) - len(terms)
        print(f"  {kind:12s} {len(terms):4d} mined + {manual_only:3d} manual -> {path.name}")
        if args.report:
            print(f"               coverage of indexed titles: {coverage(titles, combined):.1%}")
            print(f"               sample: {', '.join(sorted(terms)[:8])}")

    if args.report:
        numeric = float(titles.fillna("").astype(str).str.contains(_NUMERIC_SPEC_RE).mean())
        print(f"\n  numeric spec coverage of indexed titles: {numeric:.1%}")
        print("  Low coverage is the point. It is why these feed explanation rather than")
        print("  ranking: a requirement-match boost was built against them, measured flat,")
        print("  and removed. No requirement field is ever used as a filter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
