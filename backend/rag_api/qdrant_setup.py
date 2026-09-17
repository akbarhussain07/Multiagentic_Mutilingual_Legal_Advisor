"""Qdrant collection: dense bge-m3 + sparse BM25 with IDF, plus payload indexes."""
from __future__ import annotations

import logging
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from . import rag_config

logger = logging.getLogger(__name__)

COLLECTION_NAME = rag_config.QDRANT_COLLECTION
DENSE_DIM = rag_config.EMBEDDING_DIMENSION

PAYLOAD_INDEXES: list[tuple[str, str]] = [
    ("legal_system", "keyword"),
    ("content_type", "keyword"),
    ("dataset", "keyword"),
    ("province", "keyword"),
    ("jurisdiction", "keyword"),
    ("language", "keyword"),
    ("doc_id", "keyword"),
    ("chunk_id", "keyword"),
    ("source_path", "keyword"),
    ("view_mode", "keyword"),
]


def get_qdrant_client() -> QdrantClient:
    kwargs: dict[str, Any] = {"url": rag_config.QDRANT_URL}
    if rag_config.QDRANT_API_KEY:
        kwargs["api_key"] = rag_config.QDRANT_API_KEY
    return QdrantClient(**kwargs)


def setup_collection(client: Optional[QdrantClient] = None, recreate: bool = False) -> None:
    client = client or get_qdrant_client()
    exists = client.collection_exists(COLLECTION_NAME)

    if exists and recreate:
        logger.warning("Recreating Qdrant collection %s", COLLECTION_NAME)
        client.delete_collection(COLLECTION_NAME)
        exists = False

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={
                "dense": VectorParams(
                    size=DENSE_DIM,
                    distance=Distance.COSINE,
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                )
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(on_disk=False),
                    modifier=Modifier.IDF,
                )
            },
        )
        logger.info("Created hybrid collection %s", COLLECTION_NAME)
    else:
        logger.info("Collection %s already exists", COLLECTION_NAME)

    _ensure_payload_indexes(client)


def _ensure_payload_indexes(client: QdrantClient) -> None:
    for field, schema in PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
        except (UnexpectedResponse, ValueError) as exc:
            message = str(exc).lower()
            if "already" in message or "exists" in message or "duplicate" in message:
                continue
            logger.warning("Payload index create failed for %s: %s", field, exc)


def check_qdrant_health(client: Optional[QdrantClient] = None) -> dict[str, Any]:
    try:
        client = client or get_qdrant_client()
        exists = client.collection_exists(COLLECTION_NAME)
        payload = {
            "connected": True,
            "qdrant_connected": True,
            "collection": COLLECTION_NAME,
            "collection_exists": exists,
            "dense_dim": DENSE_DIM,
            "hybrid": True,
            "fusion": "RRF",
            "payload_indexes": [name for name, _ in PAYLOAD_INDEXES],
        }
        if exists:
            info = client.get_collection(COLLECTION_NAME)
            payload["points_count"] = getattr(info, "points_count", None)
        return payload
    except Exception as exc:
        logger.exception("Qdrant health check failed")
        return {
            "connected": False,
            "qdrant_connected": False,
            "collection": COLLECTION_NAME,
            "error": str(exc),
        }
