"""Central configuration for the semantic search workstream.

Every path is derived from the repo root so the package works regardless of the
current working directory.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "IS_Standards_Data"
PKG_DIR = Path(__file__).resolve().parent
WORK_DIR = PKG_DIR.parent

STANDARDS_CSV = DATA_DIR / "standards.csv"
EDGES_CSV = DATA_DIR / "edges.csv"

ARTIFACTS = WORK_DIR / "artifacts"
CORPUS_PARQUET = ARTIFACTS / "corpus.parquet"
LOOKUP_PARQUET = ARTIFACTS / "lookup.parquet"
EMBEDDINGS_NPY = ARTIFACTS / "embeddings.npy"
FAISS_INDEX = ARTIFACTS / "index.faiss"
BM25_PICKLE = ARTIFACTS / "bm25.pkl"
SCOPE_BM25_PICKLE = ARTIFACTS / "bm25_scope.pkl"
INDEX_META = ARTIFACTS / "index_meta.json"

CURATED_ALIASES = WORK_DIR / "data" / "aliases.csv"
EVAL_SET = WORK_DIR / "data" / "eval_set.jsonl"            # hand-written, see README section 8
EVAL_TENDERS = WORK_DIR / "data" / "eval_tenders.jsonl"    # real tender BOQ lines, 09_build_tender_eval.py

# Clause 1 (Scope) from the BSB Edge preview pages, see data/SCOPE_TEXT.md.
# Only `ok` rows are used, and of those only rows whose scope repeats enough of
# the title's content words: below 0.35 is where bad OCR and mis-scraped pages
# concentrate (SCOPE_TEXT.md section 2).
SCOPE_TEXT_CSV = WORK_DIR / "data" / "scope_text.csv"
SCOPE_MIN_TITLE_OVERLAP = 0.35

# --- models (all run locally on CPU; downloaded once, then cached) ---
# bge-small is 384-dim and asymmetric-friendly, which matters because our
# documents are ~8-word titles and our queries are paragraphs (trap 4).
BI_ENCODER = "BAAI/bge-small-en-v1.5"
BI_ENCODER_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# --- retrieval knobs ---
DENSE_TOP_K = 50          # candidates pulled from the vector index per line item
BM25_TOP_K = 50           # candidates pulled from the lexical index per line item
SCOPE_TOP_K = 50          # candidates pulled from the scope-text index per line item
FUSION_TOP_K = 50         # size of the fused list handed to the cross-encoder
RRF_K = 60                # reciprocal-rank-fusion damping constant
FINAL_TOP_K = 10

# The cross-encoder is built and available but off by default: it measurably
# lowers Recall@5 on the current evaluation set. Turn it on to re-measure
# once the evaluation set is replaced with real tender lines.
USE_RERANKER = False

# The scope-text BM25 is built and available as a third RRF list but off by
# default: at equal weight it dropped Recall@5 from 0.909 to 0.736, because it
# covers under half the index and lifts every covered standard it matches.
# Scope text still reaches the ranking through the embedded text, which is
# where it measured as a win. See README section 7.
USE_SCOPE_RETRIEVER = False

# --- metadata boosts (trap 2: boosts, never hard filters) ---
BOOST_PRODUCT_SPEC = 0.06       # procurement asks for products, not test methods
BOOST_METHODS_OF_TESTS = -0.03  # mild demotion; still reachable
BOOST_MANDATORY_CERT = 0.03
BOOST_RECENCY_MAX = 0.02        # linear over RECENCY_FLOOR..current year
RECENCY_FLOOR = 1980
# A requirement-match boost on material and property terms was built, measured
# and removed: it left Recall@5 and Recall@10 unchanged and cost Recall@1.
# See README section 7. Requirements are still extracted and reported; they
# just do not move the ranking.

# The largest boost any one candidate can collect. Scores are divided by
# (1 + this) so a fully boosted top hit reaches 1.0 and nothing has to be
# clipped - clipping was flattening the whole top of the list to 1.000.
MAX_TOTAL_BOOST = BOOST_PRODUCT_SPEC + BOOST_MANDATORY_CERT + BOOST_RECENCY_MAX

SCORE_CITED = 1.0               # a cited "IS 1786" outranks everything the retriever guessed
SCORE_CITED_PART = 0.95         # a part of a cited, since-split standard
MAX_PINNED_PARTS = 3            # cap on parts pinned for a bare cited number

# --- relevance tiers ---
# Presentation over the existing score, not a new signal. Thresholds are fitted
# to data/eval_set.jsonl by 06_calibrate_tiers.py, not chosen as round numbers.
TIER_HIGH = "Highly relevant"
TIER_RELATED = "Related"
TIER_POSSIBLE = "Possibly relevant"
TIER_HIGH_MIN = 0.96
TIER_RELATED_MIN = 0.81
