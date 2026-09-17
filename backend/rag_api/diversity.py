"""Per-document diversity ordering after rerank."""
from __future__ import annotations

from typing import Any


def _split_by_doc_cap(
    chunks: list[dict[str, Any]],
    max_per_doc: int,
    key: str = "doc_id",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[Any, int] = {}
    head: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []
    for chunk in chunks:
        doc = chunk.get(key) or chunk.get("source") or chunk.get("chunk_id")
        count = seen.get(doc, 0)
        if count < max_per_doc:
            head.append(chunk)
            seen[doc] = count + 1
        else:
            tail.append(chunk)
    return head, tail


def cap_per_doc(
    chunks: list[dict[str, Any]],
    max_per_doc: int,
    key: str = "doc_id",
) -> list[dict[str, Any]]:
    if max_per_doc <= 0:
        return chunks
    head, _ = _split_by_doc_cap(chunks, max_per_doc, key)
    return head


def order_breadth_first(
    chunks: list[dict[str, Any]],
    max_per_doc: int,
    key: str = "doc_id",
) -> list[dict[str, Any]]:
    """Diverse subset first, over-cap chunks after. Nothing is discarded."""
    if max_per_doc <= 0:
        return chunks
    head, tail = _split_by_doc_cap(chunks, max_per_doc, key)
    return head + tail
