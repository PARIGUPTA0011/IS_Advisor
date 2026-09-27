"""Hybrid retrieval: BM25 + dense + scope BM25, fused, boosted, optionally reranked.

This module is the end of the semantic search workstream. It returns a ranked
list of candidate standards and stops there - allied standards, replacement
chains and certification live in the knowledge graph workstream.

Retrieval itself is English-only and stays that way: `query.parse_document`
hands over English line items whatever language they arrived in, so BM25, the
bi-encoder, the boosts and the citation resolver all see exactly the text they
were measured on. The only language-aware step here is the last one -
`_localise` translates what is displayed, after the ranking is decided, and
never touches an IS number.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import config
from . import query as query_mod
from .lexical import BM25Index, tokenize
from .requirements import Requirements, extract as extract_requirements

_CURRENT_YEAR = _dt.date.today().year


@dataclass
class Candidate:
    kys_id: int
    is_number: str
    title: str
    score: float
    why: str
    aspect: str | None = None
    dept_code: str | None = None
    mandatory_cert: bool = False
    tier: str = ""
    # Present only when the query was not in English. `is_number` and `title`
    # keep their English values in every case: the number is an identifier and
    # the title is the standard's legal name, which a tender has to quote as it
    # stands. The localised strings sit beside them, additively, so an existing
    # consumer of this contract reads exactly the fields it already read.
    title_localized: str | None = None
    why_localized: str | None = None
    tier_localized: str | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        out["score"] = round(float(self.score), 4)
        out["tier"] = self.tier or tier_for(self.score)
        return {k: v for k, v in out.items() if not (k.endswith("_localized") and v is None)}


@dataclass
class CitedStandard:
    """A standard the tender named outright, resolved against the full dataset."""

    cited_as: str
    kys_id: int | None
    is_number: str | None
    title: str | None
    status: str | None
    in_index: bool
    replaced_by_is: str | None = None
    successor_parts: list[str] = field(default_factory=list)
    note: str = ""
    title_localized: str | None = None
    note_localized: str | None = None
    status_localized: str | None = None

    def to_dict(self) -> dict:
        out = asdict(self)
        return {k: v for k, v in out.items() if not (k.endswith("_localized") and v is None)}


@dataclass
class ItemResult:
    line_item: str                       # as it was typed, in the input language
    query_text: str                      # English, what retrieval actually ran on
    candidates: list[Candidate] = field(default_factory=list)
    cited_standards: list[CitedStandard] = field(default_factory=list)
    requirements: Requirements | None = None
    # Both empty/None for an English query, so the contract in README section 9
    # is unchanged for every existing consumer.
    line_item_english: str = ""
    language: dict | None = None

    def to_dict(self) -> dict:
        out = {
            "line_item": self.line_item,
            "query_text": self.query_text,
            "requirements": self.requirements.to_dict() if self.requirements else {},
            "candidates": [c.to_dict() for c in self.candidates],
            "cited_standards": [c.to_dict() for c in self.cited_standards],
        }
        if self.language:
            # Only present on a non-English query, and it carries how the
            # language was decided, not just which one it was.
            out["language"] = self.language
            out["line_item_english"] = self.line_item_english
        return out


def _rrf(rank: int) -> float:
    return 1.0 / (config.RRF_K + rank)


def tier_for(score: float) -> str:
    """Band a 0-1 score into the three tiers the product asks for."""
    if score >= config.TIER_HIGH_MIN:
        return config.TIER_HIGH
    if score >= config.TIER_RELATED_MIN:
        return config.TIER_RELATED
    return config.TIER_POSSIBLE


def _combine(relevance: float, boost: float) -> float:
    """Fold a metadata boost into a 0..1 relevance score.

    Multiplicative and divided by the maximum possible boost, so a boost can
    reorder near-ties without every well-boosted candidate landing on 1.000.
    """
    scaled = relevance * (1.0 + boost) / (1.0 + config.MAX_TOTAL_BOOST)
    return float(min(max(scaled, 0.0), 1.0))


class Retriever:
    """Owns the corpus and the indexes; one instance serves many queries."""

    def __init__(
        self,
        corpus_df: pd.DataFrame,
        bm25: BM25Index,
        dense=None,
        encoder=None,
        cross_encoder=None,
        lookup_df: pd.DataFrame | None = None,
        nlp=None,
        scope_bm25: BM25Index | None = None,
        fallback_dense=None,
    ):
        self.corpus = corpus_df.reset_index(drop=True)
        # Vectors from the multilingual fallback encoder, for lines that are
        # still not English at retrieval time. Its encoder loads on first use.
        self.fallback_dense = fallback_dense
        self._fallback_encoder = None
        self.bm25 = bm25
        # A separate keyword index over clause 1 scope text alone. It covers
        # only the standards that have a usable scope, so its row positions are
        # its own and are mapped back to the corpus through kys_id.
        self.scope_bm25 = scope_bm25
        self._pos_by_kys = {int(k): i for i, k in enumerate(self.corpus["kys_id"])}
        self.dense = dense
        self.encoder = encoder
        self.cross_encoder = cross_encoder
        self.nlp = nlp
        self.lookup = lookup_df
        self._by_base = {b: i for i, b in enumerate(self.corpus["is_base_id"])}
        # What the keyword index actually matched against; doc_text now carries
        # scope text, which would name words the keyword side never saw.
        self._doc_tokens = [set(tokenize(t)) for t in self.corpus["lexical_text"]]
        scope_col = self.corpus["scope_text"] if "scope_text" in self.corpus else [""] * len(self.corpus)
        self._scope_tokens = [set(tokenize(t)) for t in scope_col]

    # ---------------- retrieval ----------------

    def _metadata_boost(self, row_pos: int) -> tuple[float, list[str]]:
        """Boosts, never filters: newer standards are under-classified (trap 2),
        so an absent aspect must not cost a candidate its place."""
        row = self.corpus.iloc[row_pos]
        boost, reasons = 0.0, []

        aspect = str(row.get("aspect") or "").strip().lower()
        if aspect == "product specification":
            boost += config.BOOST_PRODUCT_SPEC
            reasons.append("product specification")
        elif aspect.startswith("methods of test"):
            boost += config.BOOST_METHODS_OF_TESTS

        if bool(row.get("mandatory_cert")):
            boost += config.BOOST_MANDATORY_CERT
            reasons.append("mandatory certification")

        year = row.get("is_year")
        if pd.notna(year) and year > config.RECENCY_FLOOR:
            span = max(_CURRENT_YEAR - config.RECENCY_FLOOR, 1)
            boost += config.BOOST_RECENCY_MAX * min(
                (float(year) - config.RECENCY_FLOOR) / span, 1.0
            )
        return boost, reasons

    def _overlap_reason(self, row_pos: int, query_text: str, scope: bool = False) -> str:
        """Name the query words that actually hit the document, for the `why` field."""
        vocab = self._scope_tokens[row_pos] if scope else self._doc_tokens[row_pos]
        hits = [t for t in dict.fromkeys(tokenize(query_text)) if t in vocab]
        if not hits:
            return ""
        return ("scope mentions " if scope else "matched ") + ", ".join(hits[:4])

    def _load_fallback_encoder(self):
        """Load the multilingual encoder the first time a line needs it."""
        if self._fallback_encoder is None:
            try:
                from .dense import load_encoder

                self._fallback_encoder = load_encoder(config.FALLBACK_ENCODER)
            except Exception as error:
                print(f"! multilingual encoder unavailable ({type(error).__name__}: {error}); "
                      "using the English encoder", file=sys.stderr)
                self._fallback_encoder = False
        return self._fallback_encoder or None

    def retrieve(
        self,
        text: str,
        top_k: int = config.FINAL_TOP_K,
        use_reranker: bool = config.USE_RERANKER,
        use_bm25: bool = True,
        use_dense: bool = True,
        use_scope: bool = config.USE_SCOPE_RETRIEVER,
        use_fallback_encoder: bool = False,
    ) -> list[Candidate]:
        """Rank the index against one already-cleaned line item.

        The `use_*` switches exist so the evaluation can turn each component off
        and show what it is actually worth. `use_fallback_encoder` routes the
        dense half through the multilingual encoder, for a line that is still
        not English here (see search_document).
        """
        fused: dict[int, float] = {}
        sources: dict[int, list[str]] = {}

        if use_bm25:
            for rank, (pos, _score) in enumerate(self.bm25.search(text, config.BM25_TOP_K)):
                fused[pos] = fused.get(pos, 0.0) + _rrf(rank)
                sources.setdefault(pos, []).append("keyword")

        dense_index, encoder, prefix = self.dense, self.encoder, config.BI_ENCODER_QUERY_PREFIX
        if use_fallback_encoder and self.fallback_dense is not None:
            fallback = self._load_fallback_encoder()
            if fallback is not None:
                dense_index, encoder, prefix = self.fallback_dense, fallback, config.FALLBACK_QUERY_PREFIX
        dense_active = use_dense and dense_index is not None and encoder is not None
        if dense_active:
            from .dense import encode_queries

            vector = encode_queries([text], encoder, prefix=prefix)[0]
            for rank, (pos, _score) in enumerate(dense_index.search(vector, config.DENSE_TOP_K)):
                fused[pos] = fused.get(pos, 0.0) + _rrf(rank)
                sources.setdefault(pos, []).append("semantic")

        # Third list for RRF. A standard without scope text is simply absent
        # here, which costs it nothing it had before (SCOPE_TEXT.md section 4).
        has_scope = use_scope and self.scope_bm25 is not None
        if has_scope:
            hits = self.scope_bm25.search(text, config.SCOPE_TOP_K)
            for rank, (scope_pos, _score) in enumerate(hits):
                pos = self._pos_by_kys.get(int(self.scope_bm25.kys_ids[scope_pos]))
                if pos is None:
                    continue
                fused[pos] = fused.get(pos, 0.0) + _rrf(rank)
                sources.setdefault(pos, []).append("scope")

        if not fused:
            return []

        ordered = sorted(fused.items(), key=lambda kv: -kv[1])[: config.FUSION_TOP_K]
        positions = [p for p, _ in ordered]

        if use_reranker and self.cross_encoder is not None:
            from .rerank import rerank

            base = rerank(
                text, [self.corpus["doc_text"].iloc[p] for p in positions], self.cross_encoder
            )
        else:
            # Scale against the best score any document could have scored - every
            # active retriever ranking it first - rather than against the best
            # score seen. Dividing by the observed maximum pins the top hit at
            # 1.000 on every query, which reads as certainty the ranking does
            # not have.
            n_retrievers = int(use_bm25) + int(dense_active) + int(has_scope)
            ceiling = max(n_retrievers, 1) * _rrf(0)
            base = np.array([s / ceiling for _, s in ordered], dtype="float32")

        scored: list[Candidate] = []
        for pos, relevance in zip(positions, base):
            boost, boost_reasons = self._metadata_boost(pos)
            row = self.corpus.iloc[pos]
            why_parts = []
            if "keyword" in sources.get(pos, []):
                why_parts.append(self._overlap_reason(pos, text))
            if "semantic" in sources.get(pos, []):
                why_parts.append("semantically similar title")
            if "scope" in sources.get(pos, []):
                why_parts.append(self._overlap_reason(pos, text, scope=True))
            why_parts.extend(boost_reasons)
            scored.append(
                Candidate(
                    kys_id=int(row["kys_id"]),
                    is_number=str(row["is_number"]),
                    title=str(row["title_display"]),
                    score=_combine(float(relevance), boost),
                    why="; ".join(p for p in why_parts if p) or "ranked by hybrid retrieval",
                    aspect=None if pd.isna(row.get("aspect")) else str(row.get("aspect")),
                    dept_code=None if pd.isna(row.get("dept_code")) else str(row.get("dept_code")),
                    mandatory_cert=bool(row.get("mandatory_cert")),
                )
            )
            scored[-1].tier = tier_for(scored[-1].score)
        scored.sort(key=lambda c: -c.score)
        return scored[:top_k]

    # ---------------- cited standards (trap 3) ----------------

    def resolve_citation(self, base_id: str) -> CitedStandard:
        """Look up a standard the tender named, current or long withdrawn."""
        pos = self._by_base.get(base_id)
        if pos is not None:
            row = self.corpus.iloc[pos]
            return CitedStandard(
                cited_as=base_id,
                kys_id=int(row["kys_id"]),
                is_number=str(row["is_number"]),
                title=str(row["title_display"]),
                status="current",
                in_index=True,
                note="cited standard is current; the edition shown is the latest",
            )
        if self.lookup is None:
            return CitedStandard(
                base_id, None, None, None, None, False, note="not found in the index"
            )

        parts = self._successor_parts(base_id)
        rows = self.lookup[self.lookup["is_base_id"] == base_id]
        if rows.empty:
            note = (
                f"no unsplit standard by that number; it exists as {', '.join(parts)}"
                if parts
                else "no such standard in the dataset"
            )
            return CitedStandard(
                base_id, None, None, None, None, False, successor_parts=parts, note=note
            )
        row = rows.sort_values("is_year", na_position="first").iloc[-1]
        replaced = row.get("replaced_by_is")
        note = "cited standard is withdrawn; not recommended, pass to the graph for its replacement"
        if parts:
            note += f"; it was split into {', '.join(parts)}"
        return CitedStandard(
            cited_as=base_id,
            kys_id=int(row["kys_id"]),
            is_number=str(row["is_number"]),
            title=str(row["title_display"]),
            status=str(row["status"]),
            in_index=False,
            replaced_by_is=None if pd.isna(replaced) else str(replaced),
            successor_parts=parts,
            note=note,
        )

    def _successor_parts(self, base_id: str) -> list[str]:
        """Indexed multi-part standards carrying the cited number.

        A tender still says "IS 2062" years after BIS split it into
        IS 2062 (Part 1) and (Part 2), so the bare number must reach the parts.
        """
        if "(" in base_id:
            return []
        parts = sorted(b for b in self._by_base if b.startswith(f"{base_id} ("))
        # Some numbers fan out into dozens of sections (IS 302 has 40+). Pinning
        # them all would bury the candidates the retriever actually ranked, so
        # only a short prefix is pinned; the note still records the split.
        return parts[: config.MAX_PINNED_PARTS]

    def _pin(self, base_id: str, score: float, why: str) -> Candidate:
        """Build a candidate for a standard we know is right, bypassing ranking.

        A pinned standard is top tier whatever the thresholds are set to: the
        tender named it, which is a fact rather than a ranking.
        """
        row = self.corpus.iloc[self._by_base[base_id]]
        return Candidate(
            tier=config.TIER_HIGH,
            kys_id=int(row["kys_id"]),
            is_number=str(row["is_number"]),
            title=str(row["title_display"]),
            score=score,
            why=why,
            aspect=None if pd.isna(row.get("aspect")) else str(row.get("aspect")),
            dept_code=None if pd.isna(row.get("dept_code")) else str(row.get("dept_code")),
            mandatory_cert=bool(row.get("mandatory_cert")),
        )

    # ---------------- document level ----------------

    def search_document(
        self,
        document: str,
        top_k: int = config.FINAL_TOP_K,
        use_reranker: bool = config.USE_RERANKER,
        language: str | None = None,
        multilingual: bool | None = None,
    ) -> list[ItemResult]:
        """Split a tender, retrieve per line item, and return the KG contract shape.

        `language` forces the input and output language; the default detects it
        from the document. `multilingual=False` is the English-only path, which
        is what the evaluation scripts pass so a measurement can never quietly
        become a measurement of the translator.
        """
        results: list[ItemResult] = []
        items = query_mod.parse_document(
            document, self.nlp, language=language, multilingual=multilingual
        )
        for item in items:
            # Citations come out first: with them in, "conforming to IS 269"
            # was read as a quantity of 269 tonnes. The fully stripped query
            # cannot be used instead, because it has the units removed too.
            #
            # Extraction reads the English rendering, because the quantity
            # regexes, the unit aliases and the attribute gazetteers are all
            # English. A translated `Key: value` block loses the
            # key-names-the-field shortcut - its keys are not English keys - so
            # the pairs are not passed through and the fields come from the
            # text instead.
            source_text = item.english or item.raw
            requirements = extract_requirements(
                query_mod.strip_citations(source_text),
                [] if item.translated else item.pairs,
                self.nlp,
            )
            # A line whose search text is still mostly in a non-Latin script -
            # translation switched off, unavailable or failed - goes through the
            # multilingual encoder; everything else through the English one.
            # Decided from the text itself, not from `item.translated`: glossary
            # hints make the English rendering differ from the raw line even when
            # nothing was translated, so that flag cannot tell the cases apart.
            candidates = self.retrieve(item.text, top_k=top_k, use_reranker=use_reranker,
                                       use_fallback_encoder=needs_multilingual_encoder(item.text))
            cited = [self.resolve_citation(base) for base in item.cited_is]

            # An explicitly cited, still-current standard outranks anything the
            # retriever guessed - it is not a recommendation, it is a fact.
            pinned: list[Candidate] = []
            for citation in cited:
                if citation.in_index:
                    pinned.append(
                        self._pin(
                            citation.cited_as,
                            config.SCORE_CITED,
                            f"cited explicitly as {citation.cited_as}",
                        )
                    )
                # The cited number may survive only as parts of a split standard.
                for part in citation.successor_parts:
                    pinned.append(
                        self._pin(
                            part,
                            config.SCORE_CITED_PART,
                            f"part of {citation.cited_as}, which the line item cites",
                        )
                    )
            if pinned:
                pinned_ids = {c.kys_id for c in pinned}
                candidates = pinned + [c for c in candidates if c.kys_id not in pinned_ids]
            results.append(
                ItemResult(
                    line_item=item.raw,
                    query_text=item.text,
                    candidates=candidates[:top_k],
                    cited_standards=cited,
                    requirements=requirements,
                    line_item_english=item.english if item.translated else "",
                    language=None,
                )
            )

        target = language or (items[0].language if items else None)
        return _localise(results, target)


def _localise(results: list[ItemResult], target: str | None) -> list[ItemResult]:
    """Translate what is displayed, after the ranking is decided.

    Runs last on purpose. Everything that decides an answer - retrieval,
    boosts, citation resolution - has already run on English text, so a
    translation cannot change which standards come back or in what order. It
    can only change how they read.
    """
    if not results:
        return results
    from multilingual.localize import Localizer

    localizer = Localizer(target)
    if not localizer.active:
        return results

    # One model call for every string in the response. See Localizer.prime.
    pending: list[str | None] = []
    for result in results:
        for candidate in result.candidates:
            pending.extend([candidate.why, candidate.title, candidate.tier or tier_for(candidate.score)])
        for citation in result.cited_standards:
            pending.extend([citation.note, citation.title])
    localizer.prime(pending)

    described = localizer.describe()
    for result in results:
        result.language = described
        for candidate in result.candidates:
            tier = candidate.tier or tier_for(candidate.score)
            candidate.tier_localized = localizer.plain_label(tier)
            candidate.why_localized = localizer.plain(candidate.why)
            gloss = localizer.title_gloss(candidate.title)
            candidate.title_localized = gloss.text if gloss else None
        for citation in result.cited_standards:
            citation.note_localized = localizer.plain(citation.note) if citation.note else None
            if citation.status:
                citation.status_localized = localizer.plain_label(citation.status)
            gloss = localizer.title_gloss(citation.title)
            citation.title_localized = gloss.text if gloss else None
    return results


def _embeddings_are_stale(corpus_df: pd.DataFrame) -> bool:
    """True when the stored vectors no longer describe this corpus.

    Two ways they can stop describing it, and both are checked, because both
    fail silently and produce plausible-looking rankings:

    * the document text changed since the vectors were built (fingerprint), and
    * the encoder changed since the vectors were built (model name). Switching
      from an English encoder to a multilingual one leaves a vector file of the
      right shape and the wrong meaning, and comparing a multilingual query
      vector against English-encoder document vectors returns confident
      nonsense. The fingerprint alone cannot see this: the text did not change.
    """
    if not config.INDEX_META.exists():
        return False        # nothing recorded; assume the build was consistent
    from .dense import fingerprint

    meta = json.loads(config.INDEX_META.read_text())
    stored_model = meta.get("model")
    if stored_model and stored_model != config.BI_ENCODER:
        print(
            f"! embeddings.npy was built with {stored_model}, config now asks for "
            f"{config.BI_ENCODER}",
            file=sys.stderr,
        )
        return True
    stored = meta.get("embedding_fingerprint")
    if not stored:
        return False
    return stored != fingerprint(corpus_df["doc_text"].tolist())


NON_LATIN_SHARE = 0.3   # of letters; the glossary's English hints never reach this on their own


def needs_multilingual_encoder(text: str) -> bool:
    """True when a query is still substantially non-Latin script at retrieval.

    Romanised Indic ("TMT sariya Fe500D") stays on the English encoder: it is
    Latin script, the curated trade names catch it through BM25, and the
    glossary appends the English terms.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for ch in letters if ord(ch) > 0x024F)
    return non_latin / len(letters) >= NON_LATIN_SHARE


def _fallback_is_stale(corpus_df: pd.DataFrame) -> bool:
    """The same two checks as _embeddings_are_stale, for the fallback vectors."""
    if not config.INDEX_META.exists():
        return False
    from .dense import fingerprint

    meta = json.loads(config.INDEX_META.read_text())
    if meta.get("fallback_model") != config.FALLBACK_ENCODER:
        return True
    stored = meta.get("fallback_fingerprint")
    return bool(stored) and stored != fingerprint(corpus_df["doc_text"].tolist())


def load_retriever(
    with_dense: bool = True,
    with_reranker: bool = config.USE_RERANKER,
    with_spacy: bool = True,
) -> Retriever:
    """Load prebuilt artifacts, degrading to keyword-only if models are missing."""
    corpus_df = pd.read_parquet(config.CORPUS_PARQUET)
    lookup_df = pd.read_parquet(config.LOOKUP_PARQUET) if config.LOOKUP_PARQUET.exists() else None
    bm25 = BM25Index.load()
    scope_bm25 = (
        BM25Index.load(config.SCOPE_BM25_PICKLE) if config.SCOPE_BM25_PICKLE.exists() else None
    )

    dense = encoder = cross = None
    if with_dense and config.EMBEDDINGS_NPY.exists():
        if _embeddings_are_stale(corpus_df):
            print(
                "! embeddings.npy was built from different document text - "
                "ignoring it; rerun 01_build_index.py to rebuild",
                file=sys.stderr,
            )
        else:
            try:
                from .dense import DenseIndex, load_encoder

                dense = DenseIndex.load()
                encoder = load_encoder()
            except Exception as error:
                # Said out loud rather than swallowed. This fallback is a real
                # quality change - keyword-only retrieval, and no cross-lingual
                # path at all - and the usual cause is an environment where
                # torch will not import (README section 1), which is invisible
                # from the results alone.
                print(
                    f"! dense retrieval unavailable ({type(error).__name__}: {error}); "
                    "falling back to keyword-only",
                    file=sys.stderr,
                )
                dense = encoder = None
    if with_reranker:
        try:
            from .rerank import load_cross_encoder

            cross = load_cross_encoder()
        except Exception:
            cross = None
    nlp = query_mod.load_spacy() if with_spacy else None
    fallback_dense = None
    if with_dense and getattr(config, "FALLBACK_ENCODER", None) and config.FALLBACK_EMBEDDINGS_NPY.exists():
        if _fallback_is_stale(corpus_df):
            print(
                f"! {config.FALLBACK_EMBEDDINGS_NPY.name} does not match the corpus or "
                f"{config.FALLBACK_ENCODER}; untranslated non-English lines will use the "
                "English encoder. Rerun 01_build_index.py to rebuild.",
                file=sys.stderr,
            )
        else:
            from .dense import DenseIndex

            fallback_dense = DenseIndex.load(config.FALLBACK_EMBEDDINGS_NPY)
    return Retriever(corpus_df, bm25, dense, encoder, cross, lookup_df, nlp, scope_bm25,
                     fallback_dense)
