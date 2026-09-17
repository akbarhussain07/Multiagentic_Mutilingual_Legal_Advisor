"""Language-run split, long-segment pre-split, then Chonkie semantic chunking."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from sentence_transformers import SentenceTransformer

from . import rag_config
from .language_detector import split_by_language
from .text_sanitize import sanitize_text

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    chunk_id: str
    source: str
    page_number: int
    language: str
    char_start: int = 0
    char_end: int = 0
    token_count: Optional[int] = None
    title: Optional[str] = None
    section: Optional[str] = None
    source_path: Optional[str] = None
    doc_id: Optional[str] = None
    legal_system: Optional[str] = None
    content_type: Optional[str] = None
    dataset: Optional[str] = None
    province: Optional[str] = None
    jurisdiction: Optional[str] = None
    ingestion_version: Optional[str] = None


@dataclass
class _PseudoChunk:
    text: str
    start_index: int = 0
    end_index: int = 0
    token_count: Optional[int] = None

    def __post_init__(self) -> None:
        self.end_index = len(self.text)


class SemanticLegalChunker:
    """bge-m3 semantic chunks after language-run splitting."""

    CHAR_FALLBACK_PER_SEGMENT = 6000

    def __init__(
        self,
        embedding_model: SentenceTransformer,
        chunk_size: int | None = None,
        threshold: float | None = None,
        min_chunk_chars: int | None = None,
    ) -> None:
        from chonkie import SemanticChunker

        self.min_chunk_chars = min_chunk_chars or rag_config.MIN_CHUNK_CHARS
        self.max_tokens = rag_config.MAX_TOKENS_PER_SEGMENT
        wrapped = embedding_model
        self._tokenizer = getattr(embedding_model, "tokenizer", None)
        try:
            from chonkie.embeddings import SentenceTransformerEmbeddings

            if isinstance(embedding_model, SentenceTransformer):
                wrapped = SentenceTransformerEmbeddings(model=embedding_model)
        except Exception as exc:
            logger.warning("Could not wrap SentenceTransformer for Chonkie (%s); using model as-is.", exc)

        if self._tokenizer is not None and hasattr(self._tokenizer, "deprecation_warnings"):
            self._tokenizer.deprecation_warnings[
                "sequence-length-is-longer-than-the-specified-maximum"
            ] = True

        self.chunker = SemanticChunker(
            embedding_model=wrapped,
            chunk_size=chunk_size or rag_config.CHUNK_SIZE_TOKENS,
            threshold=threshold or rag_config.CHUNK_THRESHOLD,
        )

    def chunk_pages(self, pages: list, doc_id: str) -> list[Chunk]:
        all_chunks: list[Chunk] = []
        dropped = 0
        for page in pages:
            text = self._clean_text(getattr(page, "text", "") or "")
            if not text:
                continue
            segments = split_by_language(text)
            if not segments:
                continue
            for seg_idx, (segment_text, seg_lang) in enumerate(segments):
                for sub_idx, sub_segment in enumerate(self._split_long_segment(segment_text)):
                    try:
                        raw_chunks = self.chunker.chunk(sub_segment)
                    except Exception as exc:
                        logger.warning(
                            "Semantic chunker failed on %s p%s s%s/%s: %s",
                            doc_id,
                            getattr(page, "page_number", 0),
                            seg_idx,
                            sub_idx,
                            exc,
                        )
                        raw_chunks = [_PseudoChunk(sub_segment)]
                    for index, raw in enumerate(raw_chunks):
                        chunk_text = (getattr(raw, "text", None) or str(raw)).strip()
                        if len(chunk_text) < self.min_chunk_chars:
                            dropped += 1
                            continue
                        all_chunks.append(
                            Chunk(
                                text=chunk_text,
                                chunk_id=f"{doc_id}__p{getattr(page, 'page_number', 0)}__s{seg_idx}_{sub_idx}__c{index}",
                                source=getattr(page, "source", doc_id),
                                page_number=int(getattr(page, "page_number", 0) or 0),
                                language=seg_lang,
                                char_start=getattr(raw, "start_index", 0) or 0,
                                char_end=getattr(raw, "end_index", len(chunk_text)) or len(chunk_text),
                                token_count=getattr(raw, "token_count", None),
                                title=sanitize_text(getattr(page, "title", None)),
                                section=_section_from_text(chunk_text) or getattr(page, "section", None),
                                source_path=getattr(page, "source_path", None),
                                doc_id=doc_id,
                                legal_system=getattr(page, "legal_system", None),
                                content_type=getattr(page, "content_type", None),
                                dataset=getattr(page, "dataset", None),
                                province=getattr(page, "province", None),
                                jurisdiction=getattr(page, "jurisdiction", None),
                                ingestion_version=rag_config.INGESTION_VERSION,
                            )
                        )
        if dropped:
            logger.debug("Dropped %s chunks below %s chars", dropped, self.min_chunk_chars)
        return all_chunks

    def _split_long_segment(self, text: str) -> list[str]:
        if self._tokenizer is None:
            return self._split_by_chars(text, self.CHAR_FALLBACK_PER_SEGMENT)
        return self._split_by_tokens(text, self.max_tokens)

    def _split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        total_ids = self._tokenizer.encode(text, add_special_tokens=False, truncation=False)
        if len(total_ids) <= max_tokens:
            return [text]
        paragraphs = re.split(r"\n\s*\n", text)
        pieces: list[str] = []
        buf: list[str] = []
        buf_tokens = 0
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            p_ids = self._tokenizer.encode(paragraph, add_special_tokens=False, truncation=False)
            p_tokens = len(p_ids)
            if p_tokens > max_tokens:
                if buf:
                    pieces.append("\n\n".join(buf))
                    buf, buf_tokens = [], 0
                for i in range(0, p_tokens, max_tokens):
                    pieces.append(self._tokenizer.decode(p_ids[i:i + max_tokens], skip_special_tokens=True))
                continue
            if buf_tokens + p_tokens > max_tokens and buf:
                pieces.append("\n\n".join(buf))
                buf, buf_tokens = [paragraph], p_tokens
            else:
                buf.append(paragraph)
                buf_tokens += p_tokens
        if buf:
            pieces.append("\n\n".join(buf))
        return pieces or [text]

    @staticmethod
    def _split_by_chars(text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        paragraphs = re.split(r"\n\s*\n", text)
        pieces: list[str] = []
        buf: list[str] = []
        buf_len = 0
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if len(paragraph) > max_chars:
                if buf:
                    pieces.append("\n\n".join(buf))
                    buf, buf_len = [], 0
                for i in range(0, len(paragraph), max_chars):
                    pieces.append(paragraph[i:i + max_chars])
                continue
            if buf_len + len(paragraph) + 2 > max_chars and buf:
                pieces.append("\n\n".join(buf))
                buf, buf_len = [paragraph], len(paragraph)
            else:
                buf.append(paragraph)
                buf_len += len(paragraph) + 2
        if buf:
            pieces.append("\n\n".join(buf))
        return pieces or [text]

    @staticmethod
    def _clean_text(text: str) -> str:
        text = sanitize_text(text) or ""
        text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)
        return text.strip()


def _section_from_text(text: str) -> Optional[str]:
    match = re.search(r"(?m)^#{1,4}\s+(.+?)\s*$", text)
    if match:
        return match.group(1).strip()
    match = re.search(
        r"(?i)\b(?:section|article|s\.?)\s+(\d+[A-Za-z]?)\b",
        text[:400],
    )
    if match:
        return match.group(0).strip()
    return None
