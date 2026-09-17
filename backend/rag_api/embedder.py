"""Dense bge-m3 + sparse BM25 embedder. No query:/passage: prefixes."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastembed import SparseTextEmbedding
from sentence_transformers import SentenceTransformer

from . import rag_config

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class BGEEmbedder:
    DENSE_MODEL = rag_config.EMBEDDING_MODEL
    SPARSE_MODEL = "Qdrant/bm25"

    def __init__(self) -> None:
        device = self._resolve_device(rag_config.EMBEDDING_DEVICE)
        logger.info("Loading dense model %s on %s", self.DENSE_MODEL, device)
        self.dense_model = SentenceTransformer(self.DENSE_MODEL, device=device)
        logger.info("Loading BM25 sparse model %s", self.SPARSE_MODEL)
        self.sparse_model = SparseTextEmbedding(model_name=self.SPARSE_MODEL)

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        dense_vecs = self.dense_model.encode(
            texts,
            batch_size=rag_config.EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        sparse_results = list(self.sparse_model.embed(texts))
        return [
            EmbeddingResult(
                dense=dense_vecs[i].tolist(),
                sparse_indices=sparse_results[i].indices.tolist(),
                sparse_values=sparse_results[i].values.tolist(),
            )
            for i in range(len(texts))
        ]

    def embed_query(self, query: str) -> EmbeddingResult:
        dense_vec = self.dense_model.encode(
            [query],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        sparse = list(self.sparse_model.embed([query]))[0]
        return EmbeddingResult(
            dense=dense_vec.tolist(),
            sparse_indices=sparse.indices.tolist(),
            sparse_values=sparse.values.tolist(),
        )

    @staticmethod
    def _resolve_device(pref: str) -> str:
        pref = (pref or "auto").lower()
        if pref == "cpu":
            return "cpu"
        try:
            import torch
            cuda = torch.cuda.is_available()
        except ImportError:
            cuda = False
        if pref == "cuda":
            return "cuda" if cuda else "cpu"
        return "cuda" if cuda else "cpu"
