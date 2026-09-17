"""Dense + BM25 hybrid retrieval with RRF fusion. Language is never a filter."""
from __future__ import annotations

import logging
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    Prefetch,
    SparseVector,
)

from . import rag_config
from .qdrant_setup import COLLECTION_NAME

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, client: QdrantClient, embedder) -> None:
        self.client = client
        self.embedder = embedder

    @staticmethod
    def build_filter(
        *,
        legal_system: str | None = None,
        content_types: list[str] | None = None,
        province: str | None = None,
        extra_must: list[Any] | None = None,
    ) -> Filter | None:
        conditions: list[Any] = []
        if legal_system:
            conditions.append(
                FieldCondition(key="legal_system", match=MatchValue(value=legal_system))
            )
        if content_types:
            conditions.append(
                Filter(
                    should=[
                        FieldCondition(key="content_type", match=MatchValue(value=value))
                        for value in content_types
                    ]
                )
            )
        if province:
            conditions.append(
                Filter(
                    should=[
                        FieldCondition(key="province", match=MatchValue(value=province)),
                        FieldCondition(key="jurisdiction", match=MatchValue(value="Pakistan")),
                        FieldCondition(key="jurisdiction", match=MatchValue(value="Federal")),
                    ]
                )
            )
        if extra_must:
            conditions.extend(extra_must)
        if not conditions:
            return None
        return Filter(must=conditions)

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        *,
        legal_system: str | None = None,
        content_types: list[str] | None = None,
        province: str | None = None,
        extra_must: list[Any] | None = None,
        fallback_unfiltered: bool = True,
    ) -> list[dict]:
        top_k = top_k or rag_config.RETRIEVAL_TOP_K
        query_filter = self.build_filter(
            legal_system=legal_system,
            content_types=content_types,
            province=province,
            extra_must=extra_must,
        )
        try:
            hits = self._query(query, top_k, query_filter)
        except Exception as exc:
            logger.warning("Filtered hybrid search failed (%s); retrying unfiltered.", exc)
            if not fallback_unfiltered:
                raise
            hits = self._query(query, top_k, None)
        if not hits and query_filter is not None and fallback_unfiltered:
            logger.info("Filtered hybrid search returned no points; retrying unfiltered.")
            hits = self._query(query, top_k, None)
        return hits

    def _query(self, query: str, top_k: int, query_filter: Optional[Filter]) -> list[dict]:
        query_emb = self.embedder.embed_query(query)
        results = self.client.query_points(
            collection_name=COLLECTION_NAME,
            prefetch=[
                Prefetch(
                    query=query_emb.dense,
                    using="dense",
                    limit=top_k * 2,
                    filter=query_filter,
                ),
                Prefetch(
                    query=SparseVector(
                        indices=query_emb.sparse_indices,
                        values=query_emb.sparse_values,
                    ),
                    using="sparse",
                    limit=top_k * 2,
                    filter=query_filter,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        points = getattr(results, "points", None) or []
        output: list[dict] = []
        for point in points:
            payload = point.payload or {}
            output.append(
                {
                    "chunk_id": payload.get("chunk_id"),
                    "doc_id": payload.get("doc_id"),
                    "text": payload.get("text", ""),
                    "source": payload.get("source") or payload.get("source_file", ""),
                    "page": payload.get("page_number"),
                    "language": payload.get("language"),
                    "title": payload.get("title"),
                    "section": payload.get("section") or payload.get("section_title"),
                    "source_path": payload.get("source_path"),
                    "legal_system": payload.get("legal_system"),
                    "content_type": payload.get("content_type"),
                    "dataset": payload.get("dataset"),
                    "province": payload.get("province"),
                    "jurisdiction": payload.get("jurisdiction"),
                    "score": getattr(point, "score", 0.0),
                    "payload": payload,
                }
            )
        return output
