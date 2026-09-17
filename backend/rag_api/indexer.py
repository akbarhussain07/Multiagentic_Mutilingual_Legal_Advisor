"""Upsert legal chunks into Qdrant with deterministic point IDs."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchExcept,
    MatchValue,
    PointStruct,
    SparseVector,
)

from . import rag_config
from .chunker import Chunk
from .embedder import BGEEmbedder
from .qdrant_setup import COLLECTION_NAME

logger = logging.getLogger(__name__)


class QdrantIndexer:
    def __init__(self, client: QdrantClient, embedder: BGEEmbedder) -> None:
        self.client = client
        self.embedder = embedder

    def index_chunks(self, chunks: list[Chunk], doc_id: str | None = None) -> int:
        if not chunks:
            return 0
        total = 0
        batch_size = rag_config.UPSERT_BATCH_SIZE
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            self._index_batch(batch, doc_id)
            total += len(batch)
            logger.info("Indexed %s/%s chunks", total, len(chunks))
        return total

    def index_chunks_replacing(self, chunks: list[Chunk], doc_id: str) -> int:
        if not chunks:
            self._delete_by_doc_id(doc_id)
            return 0
        total = self.index_chunks(chunks, doc_id=doc_id)
        keep_ids = [chunk.chunk_id for chunk in chunks]
        try:
            self._delete_stale_chunks(doc_id, keep_ids)
        except Exception as exc:
            logger.warning("Indexed %s chunks for %s but stale prune failed: %s", total, doc_id, exc)
        return total

    def delete_by_dataset(self, dataset: str) -> None:
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="dataset", match=MatchValue(value=dataset))]
                )
            ),
            wait=True,
        )

    def delete_by_ids(self, point_ids: list[str]) -> None:
        if not point_ids:
            return
        for start in range(0, len(point_ids), 900):
            self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=point_ids[start:start + 900],
                wait=True,
            )

    def _delete_stale_chunks(self, doc_id: str, keep_chunk_ids: list[str]) -> None:
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        FieldCondition(
                            key="chunk_id",
                            match=MatchExcept(**{"except": keep_chunk_ids}),
                        ),
                    ]
                )
            ),
            wait=True,
        )

    def _delete_by_doc_id(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                )
            ),
            wait=True,
        )

    def _index_batch(self, chunks: list[Chunk], doc_id: Optional[str]) -> None:
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedder.embed_texts(texts)
        points = []
        for chunk, emb in zip(chunks, embeddings):
            resolved_doc = doc_id or chunk.doc_id or chunk.chunk_id.split("__", 1)[0]
            payload = {
                "chunk_id": chunk.chunk_id,
                "doc_id": resolved_doc,
                "text": chunk.text,
                "source": chunk.source,
                "page_number": chunk.page_number,
                "language": chunk.language,
                "title": chunk.title,
                "section": chunk.section,
                "source_path": chunk.source_path,
                "source_file": chunk.source,
                "legal_system": chunk.legal_system,
                "content_type": chunk.content_type,
                "dataset": chunk.dataset,
                "province": chunk.province,
                "jurisdiction": chunk.jurisdiction,
                "ingestion_version": chunk.ingestion_version,
                "token_count": chunk.token_count,
            }
            payload = {key: value for key, value in payload.items() if value not in (None, "")}
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)),
                    vector={
                        "dense": emb.dense,
                        "sparse": SparseVector(
                            indices=emb.sparse_indices,
                            values=emb.sparse_values,
                        ),
                    },
                    payload=payload,
                )
            )
        self.client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
