"""PyMuPDF extraction with running-header/page-number stripping and optional OCR."""
from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pymupdf

from .text_sanitize import sanitize_text

logger = logging.getLogger(__name__)

try:
    pymupdf.TOOLS.mupdf_display_errors(False)
except AttributeError:
    pass

_PAGE_NUMBER_RE = re.compile(
    r"^(?:"
    r"\d+\s+(?:out\s+)?of\s+\d+"
    r"|page\s+\d+(?:\s+of\s+\d+)?"
    r"|p\.?\s*\d+"
    r"|[-–—]\s*\d+\s*[-–—]"
    r"|\d{1,4}"
    r")$"
)


@dataclass
class ExtractedPage:
    text: str
    page_number: int
    source: str
    is_ocr: bool = False
    title: Optional[str] = None
    section: Optional[str] = None
    source_path: Optional[str] = None
    legal_system: Optional[str] = None
    content_type: Optional[str] = None
    dataset: Optional[str] = None
    province: Optional[str] = None
    jurisdiction: Optional[str] = None


class PDFExtractor:
    MIN_TEXT_LENGTH = 50

    def extract(self, pdf_path: str) -> list[ExtractedPage]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {file_path_label(path)}")

        doc = pymupdf.open(str(path))
        pages: list[ExtractedPage] = []
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                raw_text = (page.get_text("text") or "").strip()
                is_ocr = False
                if len(raw_text) < self.MIN_TEXT_LENGTH:
                    ocr_text = self._try_ocr(page)
                    if ocr_text:
                        raw_text = ocr_text
                        is_ocr = True
                cleaned = sanitize_text(raw_text) or ""
                if not cleaned:
                    continue
                pages.append(
                    ExtractedPage(
                        text=cleaned,
                        page_number=page_num + 1,
                        source=path.name,
                        is_ocr=is_ocr,
                    )
                )
        finally:
            doc.close()

        pages = self._strip_running_headers_footers(pages, path.name)
        return [page for page in pages if page.text.strip()]

    @staticmethod
    def _try_ocr(page) -> str:
        try:
            textpage = page.get_textpage_ocr()  # requires Tesseract when present
            text = page.get_text("text", textpage=textpage) or ""
            return text.strip()
        except Exception as exc:
            logger.info(
                "OCR fallback unavailable on page %s: %s",
                getattr(page, "number", "?"),
                exc,
            )
            return ""

    @staticmethod
    def _strip_running_headers_footers(
        pages: list[ExtractedPage],
        doc_name: str = "",
        *,
        min_pages: int = 4,
        repeat_frac: float = 0.6,
        edge_lines: int = 3,
        max_len: int = 120,
    ) -> list[ExtractedPage]:
        if len(pages) < min_pages:
            return pages

        def _norm(line: str) -> str:
            return re.sub(r"\s+", " ", line.strip().lower())

        def _edge_indices(lines: list[str]) -> set[int]:
            nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
            return set(nonempty[:edge_lines]) | set(nonempty[-edge_lines:])

        edge_counter: Counter = Counter()
        for page in pages:
            lines = page.text.splitlines()
            for index in _edge_indices(lines):
                normalized = _norm(lines[index])
                if 0 < len(normalized) <= max_len:
                    edge_counter[normalized] += 1

        threshold = max(min_pages, int(len(pages) * repeat_frac))
        boiler = {text for text, count in edge_counter.items() if count >= threshold}
        removed = 0
        for page in pages:
            lines = page.text.splitlines()
            edge_idx = _edge_indices(lines)
            kept = []
            for index, line in enumerate(lines):
                if index in edge_idx:
                    normalized = _norm(line)
                    if normalized and (normalized in boiler or _PAGE_NUMBER_RE.match(normalized)):
                        removed += 1
                        continue
                kept.append(line)
            page.text = "\n".join(kept).strip()
        if removed:
            logger.info("%s: stripped %s running header/footer/page-number line(s)", doc_name, removed)
        return pages


def file_path_label(path: Path) -> str:
    return path.as_posix()
