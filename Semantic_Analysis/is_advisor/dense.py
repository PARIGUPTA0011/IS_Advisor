"""Dense retrieval with a local bi-encoder.

`sentence-transformers` runs on CPU with no API key; the model is downloaded
once and cached, after which the whole pipeline is offline. FAISS is used when
available and a plain numpy dot product otherwise - at 23k x 384 floats an
exhaustive search is ~35 MB and still returns in milliseconds, so the fallback
costs nothing in practice.
"""
from __future__ import annotations

import numpy as np

from . import config

_model_cache: dict[str, object] = {}


def fingerprint(texts: list[str]) -> str:
    """Hash of the embedded text, so a partial rebuild cannot silently
    leave the vectors pointing at rows that have since moved."""
    import hashlib

    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8", "replace"))
        digest.update(b"\x00")
    return digest.hexdigest()[:16]


def load_encoder(name: str = config.BI_ENCODER):
    """Load (and memoise) the bi-encoder. Raises if sentence-transformers is absent."""
    if name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        _model_cache[name] = SentenceTransformer(name, device="cpu")
    return _model_cache[name]


def encode_documents(texts: list[str], model=None, batch_size: int = 64, show_progress: bool = True) -> np.ndarray:
    model = model or load_encoder()
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,      # cosine similarity becomes a dot product
        show_progress_bar=show_progress,
    )
    return vectors.astype("float32")


def encode_queries(texts: list[str], model=None) -> np.ndarray:
    """Encode queries, applying the model's retrieval prefix where it has one."""
    model = model or load_encoder()
    prefix = config.BI_ENCODER_QUERY_PREFIX if "bge" in config.BI_ENCODER.lower() else ""
    prepared = [f"{prefix}{t}" for t in texts]
    vectors = model.encode(
        prepared, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False
    )
    return vectors.astype("float32")


class DenseIndex:
    """Vector index over the corpus, FAISS-backed when FAISS is installed."""

    def __init__(self, embeddings: np.ndarray):
        self.embeddings = np.ascontiguousarray(embeddings.astype("float32"))
        self._faiss_index = None
        try:
            import faiss

            index = faiss.IndexFlatIP(self.embeddings.shape[1])
            index.add(self.embeddings)
            self._faiss_index = index
        except Exception:
            self._faiss_index = None      # numpy fallback below

    @property
    def backend(self) -> str:
        return "faiss" if self._faiss_index is not None else "numpy"

    def search(self, query_vector: np.ndarray, top_k: int = config.DENSE_TOP_K) -> list[tuple[int, float]]:
        query_vector = np.ascontiguousarray(query_vector.reshape(1, -1).astype("float32"))
        top_k = min(top_k, len(self.embeddings))
        if self._faiss_index is not None:
            scores, ids = self._faiss_index.search(query_vector, top_k)
            return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]
        scores = self.embeddings @ query_vector[0]
        top = np.argpartition(-scores, top_k - 1)[:top_k]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top]

    def save(self, path=config.EMBEDDINGS_NPY) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, self.embeddings)

    @staticmethod
    def load(path=config.EMBEDDINGS_NPY) -> "DenseIndex":
        return DenseIndex(np.load(path))
