"""Multilingual cross-encoder reranker."""
from __future__ import annotations

import logging

from sentence_transformers import CrossEncoder

from . import rag_config

logger = logging.getLogger(__name__)


class BGEReranker:
    MODEL = rag_config.RERANKER_MODEL

    def __init__(self) -> None:
        device = _resolve_device(rag_config.EMBEDDING_DEVICE)
        max_length = rag_config.RERANKER_MAX_LENGTH
        logger.info("Loading reranker %s on %s (max_length=%s)", self.MODEL, device, max_length)
        self.model = CrossEncoder(self.MODEL, device=device, max_length=max_length)

    def rerank(self, query: str, chunks: list[dict], top_k: int | None = None) -> list[dict]:
        if not chunks:
            return []
        if top_k is None:
            top_k = rag_config.RERANK_TOP_K
        pairs = [(query, chunk.get("text") or "") for chunk in chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)
        ranked = sorted(chunks, key=lambda item: item["rerank_score"], reverse=True)
        return ranked[:top_k]


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
