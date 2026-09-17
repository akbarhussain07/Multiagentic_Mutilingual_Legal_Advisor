"""Ingest Markdown and PDF legal sources into the Qdrant legal-advisor collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

import frontmatter
from dotenv import load_dotenv

from . import rag_config
from .chunker import Chunk, SemanticLegalChunker
from .embedder import BGEEmbedder
from .indexer import QdrantIndexer
from .pdf_extractor import ExtractedPage, PDFExtractor
from .qdrant_setup import get_qdrant_client, setup_collection
from .text_sanitize import sanitize_text

logger = logging.getLogger("legal_ingestion")
DatasetName = Literal["pakistani", "islamic", "procedure"]
INGESTION_VERSION = rag_config.INGESTION_VERSION


@dataclass(frozen=True)
class DatasetConfig:
    name: DatasetName
    source_dir: Path
    legal_system: str
    default_content_type: str


@dataclass
class PreparedSource:
    dataset: DatasetName
    source_path: str
    source_hash: str
    chunks: List[Chunk]


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: Dict[str, Any] = {
            "ingestion_version": INGESTION_VERSION,
            "datasets": {},
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = loaded
        except Exception as exc:
            logger.warning("Could not read manifest %s: %s", self.path, exc)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def get_source(self, dataset: DatasetName, source_path: str) -> Optional[Dict[str, Any]]:
        return self.data.get("datasets", {}).get(dataset, {}).get(source_path)

    def set_source(
        self,
        dataset: DatasetName,
        source_path: str,
        source_hash: str,
        vector_ids: List[str],
    ) -> None:
        dataset_map = self.data.setdefault("datasets", {}).setdefault(dataset, {})
        dataset_map[source_path] = {
            "source_hash": source_hash,
            "vector_ids": vector_ids,
            "collection": rag_config.QDRANT_COLLECTION,
            "ingestion_version": INGESTION_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def remove_source(self, dataset: DatasetName, source_path: str) -> None:
        self.data.setdefault("datasets", {}).setdefault(dataset, {}).pop(source_path, None)

    def dataset_sources(self, dataset: DatasetName) -> Dict[str, Dict[str, Any]]:
        return self.data.setdefault("datasets", {}).setdefault(dataset, {})


class LegalIngestionPipeline:
    def __init__(self) -> None:
        default_root = Path(__file__).resolve().parent.parent
        load_dotenv(default_root / ".env")
        load_dotenv(default_root / "env")
        self.project_root = Path(os.getenv("PROJECT_ROOT", default_root)).resolve()
        self.data_root = self._resolve_path(os.getenv("MARKDOWN_DATA_ROOT", "./data"))
        self.manifest = ManifestStore(
            self._resolve_path(os.getenv("INGESTION_MANIFEST_PATH", "./data/ingestion_manifest.json"))
        )
        self.client = get_qdrant_client()
        setup_collection(self.client)
        self.embedder = BGEEmbedder()
        self.chunker = SemanticLegalChunker(embedding_model=self.embedder.dense_model)
        self.indexer = QdrantIndexer(self.client, self.embedder)
        self.pdf_extractor = PDFExtractor()
        self.datasets = self._build_dataset_configs()

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _dataset_dir(self, env_name: str, *candidates: str) -> Path:
        override = os.getenv(env_name)
        if override:
            return self.data_root / override
        for name in candidates:
            path = self.data_root / name
            if path.exists():
                return path
        return self.data_root / candidates[0]

    def _build_dataset_configs(self) -> Dict[DatasetName, DatasetConfig]:
        return {
            "pakistani": DatasetConfig(
                name="pakistani",
                source_dir=self._dataset_dir("PAKISTANI_FOLDER", "Pakistan", "pakistani"),
                legal_system="Pakistani",
                default_content_type="statute",
            ),
            "islamic": DatasetConfig(
                name="islamic",
                source_dir=self.data_root / os.getenv("ISLAMIC_FOLDER", "islamic"),
                legal_system="Islamic",
                default_content_type="fiqh",
            ),
            "procedure": DatasetConfig(
                name="procedure",
                source_dir=self._dataset_dir("PROCEDURE_FOLDER", "Procedure", "procedure"),
                legal_system="Pakistani",
                default_content_type="procedure",
            ),
        }

    def discover_files(self, config: DatasetConfig) -> List[Path]:
        if not config.source_dir.exists():
            logger.warning("Dataset folder does not exist: %s", config.source_dir)
            return []
        files = [
            path
            for path in config.source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".pdf"}
        ]
        return sorted(files)

    def prepare_file(self, config: DatasetConfig, file_path: Path) -> PreparedSource:
        relative_path = file_path.relative_to(self.project_root).as_posix()
        raw_bytes = file_path.read_bytes()
        source_hash = hashlib.sha256(raw_bytes).hexdigest()
        doc_id = f"{config.name}:{relative_path}"

        if file_path.suffix.lower() == ".pdf":
            pages = self.pdf_extractor.extract(str(file_path))
            title = file_path.stem.replace("_", " ").replace("-", " ")
            for page in pages:
                page.title = title
                page.source_path = relative_path
                page.legal_system = config.legal_system
                page.content_type = config.default_content_type
                page.dataset = config.name
        else:
            raw_text = file_path.read_text(encoding="utf-8-sig")
            parsed = frontmatter.loads(raw_text)
            markdown_body = sanitize_text(parsed.content) or ""
            if not markdown_body.strip():
                raise ValueError(f"Markdown body is empty: {file_path}")
            metadata = _normalize_metadata(parsed.metadata or {})
            title = str(
                metadata.get("title")
                or _first_h1(markdown_body)
                or file_path.stem.replace("_", " ").replace("-", " ")
            ).strip()
            pages = [
                ExtractedPage(
                    text=markdown_body,
                    page_number=1,
                    source=file_path.name,
                    title=title,
                    section=str(metadata.get("section") or "") or None,
                    source_path=relative_path,
                    legal_system=str(metadata.get("legal_system") or config.legal_system),
                    content_type=str(
                        metadata.get("content_type")
                        or metadata.get("document_type")
                        or config.default_content_type
                    ),
                    dataset=config.name,
                    province=str(metadata.get("province") or "") or None,
                    jurisdiction=str(metadata.get("jurisdiction") or "") or None,
                )
            ]

        chunks = self.chunker.chunk_pages(pages, doc_id=doc_id)
        if not chunks:
            raise ValueError(f"No chunks produced for {file_path}")
        for chunk in chunks:
            chunk.legal_system = chunk.legal_system or config.legal_system
            chunk.content_type = chunk.content_type or config.default_content_type
            chunk.dataset = config.name
            chunk.source_path = relative_path
            chunk.doc_id = doc_id
            chunk.ingestion_version = INGESTION_VERSION
        return PreparedSource(config.name, relative_path, source_hash, chunks)

    def ingest_dataset(
        self,
        dataset: DatasetName,
        *,
        force: bool = False,
        dry_run: bool = False,
        delete_missing: bool = True,
        only: Optional[Sequence[str]] = None,
    ) -> Dict[str, int]:
        config = self.datasets[dataset]
        files = self.discover_files(config)
        if only:
            wanted = {name.strip().lower() for name in only if str(name).strip()}
            files = [path for path in files if path.name.lower() in wanted]
            if not files:
                logger.warning("No files matched --only for dataset %s: %s", dataset, sorted(wanted))
            delete_missing = False
        discovered_paths = {
            path.relative_to(self.project_root).as_posix() for path in files
        }
        stats = {
            "files_found": len(files),
            "files_ingested": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "chunks_upserted": 0,
            "vectors_deleted": 0,
        }

        for file_number, file_path in enumerate(files, start=1):
            relative_path = file_path.relative_to(self.project_root).as_posix()
            try:
                source_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                old_record = self.manifest.get_source(dataset, relative_path)
                if (
                    not force
                    and old_record
                    and old_record.get("source_hash") == source_hash
                    and old_record.get("ingestion_version") == INGESTION_VERSION
                ):
                    logger.info("[%s/%s] Unchanged, skipping: %s", file_number, len(files), relative_path)
                    stats["files_skipped"] += 1
                    continue

                prepared = self.prepare_file(config, file_path)
                logger.info(
                    "[%s/%s] Prepared %s chunks: %s",
                    file_number,
                    len(files),
                    len(prepared.chunks),
                    relative_path,
                )
                if dry_run:
                    stats["files_ingested"] += 1
                    stats["chunks_upserted"] += len(prepared.chunks)
                    continue

                doc_id = f"{dataset}:{relative_path}"
                self.indexer.index_chunks_replacing(prepared.chunks, doc_id=doc_id)
                vector_ids = [chunk.chunk_id for chunk in prepared.chunks]
                self.manifest.set_source(dataset, relative_path, prepared.source_hash, vector_ids)
                self.manifest.save()
                stats["files_ingested"] += 1
                stats["chunks_upserted"] += len(prepared.chunks)
            except Exception as exc:
                stats["files_failed"] += 1
                logger.exception("Failed to ingest %s: %s", relative_path, exc)

        if delete_missing and not dry_run:
            for old_source_path, record in dict(self.manifest.dataset_sources(dataset)).items():
                if old_source_path in discovered_paths:
                    continue
                stale_ids = list(record.get("vector_ids", []))
                if stale_ids:
                    logger.info("Deleting vectors for removed source %s", old_source_path)
                    try:
                        self.indexer._delete_by_doc_id(f"{dataset}:{old_source_path}")
                        stats["vectors_deleted"] += len(stale_ids)
                    except Exception as exc:
                        logger.warning("Could not delete removed source %s: %s", old_source_path, exc)
                self.manifest.remove_source(dataset, old_source_path)
                self.manifest.save()
        return stats

    def clear_dataset(self, dataset: DatasetName) -> None:
        logger.warning("Deleting all Qdrant points for dataset %s", dataset)
        self.indexer.delete_by_dataset(dataset)
        self.manifest.data.setdefault("datasets", {})[dataset] = {}
        self.manifest.save()

    def run(
        self,
        datasets: Sequence[DatasetName],
        *,
        force: bool,
        dry_run: bool,
        delete_missing: bool,
        clear_first: bool,
        only: Optional[Sequence[str]] = None,
    ) -> Dict[str, Dict[str, int]]:
        results: Dict[str, Dict[str, int]] = {}
        for dataset in datasets:
            if clear_first and not dry_run:
                self.clear_dataset(dataset)
            config = self.datasets[dataset]
            logger.info("=" * 72)
            logger.info("DATASET: %s  legal_system=%s", dataset.upper(), config.legal_system)
            logger.info("Source: %s", config.source_dir)
            results[dataset] = self.ingest_dataset(
                dataset,
                force=force,
                dry_run=dry_run,
                delete_missing=delete_missing,
                only=only,
            )
        return results


def _first_h1(markdown_body: str) -> Optional[str]:
    match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown_body)
    return match.group(1).strip() if match else None


def _normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for raw_key, raw_value in (metadata or {}).items():
        key = re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]+", "_", str(raw_key).strip().lower())).strip("_")
        if not key or raw_value is None:
            continue
        if isinstance(raw_value, bool):
            normalized[key] = raw_value
        elif isinstance(raw_value, (int, float)):
            normalized[key] = raw_value
        elif isinstance(raw_value, str):
            value = raw_value.strip()
            if value:
                normalized[key] = value
        elif isinstance(raw_value, (list, tuple, set)):
            values = [str(item).strip() for item in raw_value if str(item).strip()]
            if values:
                normalized[key] = values
        else:
            normalized[key] = json.dumps(raw_value, ensure_ascii=False, sort_keys=True)
    return normalized


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def start_ingestion_thread(
    file_path: str,
    original_name: str,
    law_type: str,
    task_id: str,
) -> threading.Thread:
    dataset_aliases: Dict[str, DatasetName] = {
        "pakistani": "pakistani",
        "pakistan": "pakistani",
        "islamic": "islamic",
        "procedure": "procedure",
    }
    dataset = dataset_aliases.get((law_type or "").strip().lower())

    def update_task(**values: Any) -> None:
        from django.core.cache import cache

        key = f"task_{task_id}"
        current = cache.get(key, {})
        cache.set(key, {**current, **values}, 3600)

    def worker() -> None:
        source = Path(file_path)
        destination: Optional[Path] = None
        try:
            if dataset is None:
                raise ValueError("law_type must be Pakistani, Islamic, or Procedure.")
            suffix = source.suffix.lower()
            if suffix not in {".md", ".markdown", ".pdf"}:
                raise ValueError("Upload Markdown (.md) or PDF (.pdf) files.")

            update_task(status="preparing", progress=10)
            pipeline = LegalIngestionPipeline()
            config = pipeline.datasets[dataset]
            config.source_dir.mkdir(parents=True, exist_ok=True)
            destination = config.source_dir / Path(original_name).name
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)

            update_task(status="indexing", progress=35)
            result = pipeline.ingest_dataset(dataset, force=True, delete_missing=False)
            if result["files_failed"]:
                raise RuntimeError(f"{result['files_failed']} document(s) failed to ingest.")
            update_task(status="completed", progress=100, result=result)
        except Exception as exc:
            logger.exception("Upload ingestion task %s failed", task_id)
            update_task(status="failed", progress=100, error=str(exc))
        finally:
            try:
                if source.exists() and (
                    destination is None or source.resolve() != destination.resolve()
                ):
                    source.unlink()
            except OSError:
                logger.warning("Could not remove temporary upload %s", source)

    thread = threading.Thread(target=worker, name=f"ingestion-{task_id}", daemon=True)
    thread.start()
    return thread


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Pakistani and Islamic legal Markdown/PDF into Qdrant."
    )
    parser.add_argument("--dataset", choices=["all", "pakistani", "islamic", "procedure"], default="all")
    parser.add_argument("--force", action="store_true", help="Reprocess unchanged files.")
    parser.add_argument("--dry-run", action="store_true", help="Chunk without uploading.")
    parser.add_argument("--keep-missing", action="store_true", help="Do not delete vectors for removed files.")
    parser.add_argument("--clear-first", action="store_true", help="Delete selected dataset points before ingestion.")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="FILENAME",
        help="Ingest only these filenames (repeatable). Implies --keep-missing.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    selected: List[DatasetName] = (
        ["pakistani", "islamic", "procedure"] if args.dataset == "all" else [args.dataset]
    )
    try:
        pipeline = LegalIngestionPipeline()
        results = pipeline.run(
            selected,
            force=args.force,
            dry_run=args.dry_run,
            delete_missing=not args.keep_missing and not args.only,
            clear_first=args.clear_first,
            only=args.only or None,
        )
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        return 1
    print("\nINGESTION SUMMARY")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
