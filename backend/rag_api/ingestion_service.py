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
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence

import frontmatter
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec
from transformers import AutoTokenizer

logger = logging.getLogger("property_ingestion")
DatasetName = Literal["pakistani", "islamic", "procedure"]
INGESTION_VERSION = "property-ingestion-v1"
E5_PASSAGE_PREFIX = "passage: "


@dataclass(frozen=True)
class DatasetConfig:
    name: DatasetName
    source_dir: Path
    index_name: str
    namespace: str
    legal_system: str
    default_content_type: str


@dataclass
class PreparedSource:
    dataset: DatasetName
    source_path: str
    source_hash: str
    chunks: List[Document]


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
        index_name: str,
        namespace: str,
    ) -> None:
        dataset_map = self.data.setdefault("datasets", {}).setdefault(dataset, {})
        dataset_map[source_path] = {
            "source_hash": source_hash,
            "vector_ids": vector_ids,
            "index_name": index_name,
            "namespace": namespace,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def remove_source(self, dataset: DatasetName, source_path: str) -> None:
        self.data.setdefault("datasets", {}).setdefault(dataset, {}).pop(source_path, None)

    def dataset_sources(self, dataset: DatasetName) -> Dict[str, Dict[str, Any]]:
        return self.data.setdefault("datasets", {}).setdefault(dataset, {})


class PropertyMarkdownIngestionPipeline:
    def __init__(self) -> None:
        load_dotenv()
        default_root = Path(__file__).resolve().parent.parent
        self.project_root = Path(os.getenv("PROJECT_ROOT", default_root)).resolve()
        self.data_root = self._resolve_path(os.getenv("MARKDOWN_DATA_ROOT", "./data"))
        self.manifest = ManifestStore(
            self._resolve_path(os.getenv("INGESTION_MANIFEST_PATH", "./data/ingestion_manifest.json"))
        )

        self.embedding_model_name = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
        self.embedding_dimension = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
        self.embedding_device = os.getenv("EMBEDDING_DEVICE", "cpu")
        self.embedding_batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
        self.chunk_size_tokens = int(os.getenv("CHUNK_SIZE_TOKENS", "420"))
        self.chunk_overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "60"))
        self.upsert_batch_size = int(os.getenv("UPSERT_BATCH_SIZE", "64"))
        self.upsert_pause_seconds = float(os.getenv("UPSERT_PAUSE_SECONDS", "0.2"))
        self.pinecone_cloud = os.getenv("PINECONE_CLOUD", "aws")
        self.pinecone_region = os.getenv("PINECONE_REGION", "us-east-1")
        self.pinecone_metric = os.getenv("PINECONE_METRIC", "cosine")
        self.text_key = os.getenv("PINECONE_TEXT_KEY", "text")

        if self.chunk_size_tokens >= 500:
            raise ValueError("CHUNK_SIZE_TOKENS should stay below 500 for multilingual-e5-large.")
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS.")

        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY is required.")

        logger.info("Loading tokenizer: %s", self.embedding_model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(self.embedding_model_name)

        logger.info("Loading embedding model: %s", self.embedding_model_name)
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.embedding_model_name,
            model_kwargs={"device": self.embedding_device},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": self.embedding_batch_size,
            },
        )

        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "header_1"),
                ("##", "header_2"),
                ("###", "header_3"),
                ("####", "header_4"),
            ],
            strip_headers=False,
            return_each_line=False,
        )

        self.body_splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=self.tokenizer,
            chunk_size=self.chunk_size_tokens,
            chunk_overlap=self.chunk_overlap_tokens,
            separators=["\n\n", "\n", "۔ ", "؟ ", "! ", ". ", "; ", "؛ ", ": ", " ", ""],
            keep_separator=True,
            add_start_index=True,
        )

        self.pc = Pinecone(api_key=api_key)
        self.datasets = self._build_dataset_configs()

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _build_dataset_configs(self) -> Dict[DatasetName, DatasetConfig]:
        return {
            "pakistani": DatasetConfig(
                name="pakistani",
                source_dir=self.data_root / os.getenv("PAKISTANI_FOLDER", "pakistani"),
                index_name=os.getenv("PINECONE_PAKISTANI_INDEX", "pakistani-property-law"),
                namespace=os.getenv("PINECONE_PAKISTANI_NAMESPACE", "documents"),
                legal_system="Pakistani",
                default_content_type="statute",
            ),
            "islamic": DatasetConfig(
                name="islamic",
                source_dir=self.data_root / os.getenv("ISLAMIC_FOLDER", "islamic"),
                index_name=os.getenv("PINECONE_ISLAMIC_INDEX", "islamic-property-law"),
                namespace=os.getenv("PINECONE_ISLAMIC_NAMESPACE", "documents"),
                legal_system="Islamic",
                default_content_type="fiqh",
            ),
            "procedure": DatasetConfig(
                name="procedure",
                source_dir=self.data_root / os.getenv("PROCEDURE_FOLDER", "procedure"),
                index_name=os.getenv("PINECONE_PROCEDURE_INDEX", "property-case-procedure"),
                namespace=os.getenv("PINECONE_PROCEDURE_NAMESPACE", "documents"),
                legal_system="Pakistani",
                default_content_type="procedure",
            ),
        }

    def ensure_indexes(self, datasets: Sequence[DatasetName]) -> None:
        existing = self._list_index_names()
        for dataset in datasets:
            config = self.datasets[dataset]
            if config.index_name not in existing:
                logger.info("Creating index %s", config.index_name)
                self.pc.create_index(
                    name=config.index_name,
                    dimension=self.embedding_dimension,
                    metric=self.pinecone_metric,
                    spec=ServerlessSpec(cloud=self.pinecone_cloud, region=self.pinecone_region),
                )
                self._wait_for_index_ready(config.index_name)
                existing.add(config.index_name)
            else:
                self._validate_index(config.index_name)

    def _list_index_names(self) -> set[str]:
        names: set[str] = set()
        for item in self.pc.list_indexes():
            name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if name:
                names.add(str(name))
        return names

    def _wait_for_index_ready(self, index_name: str, timeout_seconds: int = 180) -> None:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            description = self.pc.describe_index(index_name)
            status = getattr(description, "status", None)
            ready = bool(status.get("ready")) if isinstance(status, dict) else bool(getattr(status, "ready", False))
            if ready:
                return
            time.sleep(2)
        raise TimeoutError(f"Index {index_name} was not ready within {timeout_seconds} seconds.")

    def _validate_index(self, index_name: str) -> None:
        description = self.pc.describe_index(index_name)
        dimension = getattr(description, "dimension", None)
        metric = getattr(description, "metric", None)
        if isinstance(description, dict):
            dimension = description.get("dimension", dimension)
            metric = description.get("metric", metric)
        if int(dimension) != self.embedding_dimension:
            raise ValueError(
                f"Index {index_name} dimension is {dimension}; expected {self.embedding_dimension}."
            )
        if str(metric).lower() != self.pinecone_metric.lower():
            raise ValueError(f"Index {index_name} metric is {metric}; expected {self.pinecone_metric}.")

    def discover_files(self, config: DatasetConfig) -> List[Path]:
        if not config.source_dir.exists():
            raise FileNotFoundError(f"Dataset folder does not exist: {config.source_dir}")
        return sorted(path for path in config.source_dir.rglob("*.md") if path.is_file())

    def prepare_file(self, config: DatasetConfig, file_path: Path) -> PreparedSource:
        raw_text = file_path.read_text(encoding="utf-8-sig")
        source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        parsed = frontmatter.loads(raw_text)
        frontmatter_metadata = self._normalize_metadata(parsed.metadata)
        markdown_body = parsed.content.strip()
        if not markdown_body:
            raise ValueError(f"Markdown body is empty: {file_path}")

        relative_path = file_path.relative_to(self.project_root).as_posix()
        base_metadata = self._build_base_metadata(
            config=config,
            file_path=file_path,
            relative_path=relative_path,
            source_hash=source_hash,
            frontmatter_metadata=frontmatter_metadata,
            markdown_body=markdown_body,
        )

        sections = self.header_splitter.split_text(markdown_body)
        if not sections:
            sections = [Document(page_content=markdown_body, metadata={})]

        chunks: List[Document] = []
        for section_index, section in enumerate(sections):
            section_metadata = self._normalize_metadata(section.metadata)
            merged_metadata = {**base_metadata, **section_metadata, "section_index": section_index}
            header_path = self._header_path(section_metadata)
            section_title = self._deepest_header(section_metadata)
            if header_path:
                merged_metadata["header_path"] = header_path
            if section_title:
                merged_metadata["section_title"] = section_title

            subchunks = self.body_splitter.split_documents(
                [Document(page_content=section.page_content.strip(), metadata=merged_metadata)]
            )
            for chunk in subchunks:
                chunk.page_content = self._build_searchable_passage(chunk.page_content, chunk.metadata)
                chunks.append(chunk)

        ingested_at = datetime.now(timezone.utc).isoformat()
        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
            chunk.metadata["chunk_count"] = len(chunks)
            chunk.metadata["chunk_hash"] = hashlib.sha256(chunk.page_content.encode("utf-8")).hexdigest()
            chunk.metadata["token_count"] = len(
                self.tokenizer.encode(chunk.page_content, add_special_tokens=False, truncation=False)
            )
            chunk.metadata["ingestion_version"] = INGESTION_VERSION
            chunk.metadata["ingested_at"] = ingested_at

        return PreparedSource(config.name, relative_path, source_hash, chunks)

    def _build_base_metadata(
        self,
        *,
        config: DatasetConfig,
        file_path: Path,
        relative_path: str,
        source_hash: str,
        frontmatter_metadata: Dict[str, Any],
        markdown_body: str,
    ) -> Dict[str, Any]:
        title = str(
            frontmatter_metadata.get("title")
            or self._first_h1(markdown_body)
            or file_path.stem.replace("_", " ").replace("-", " ")
        ).strip()
        language = str(frontmatter_metadata.get("language") or self._detect_language(markdown_body))
        content_type = str(
            frontmatter_metadata.get(
                "content_type",
                frontmatter_metadata.get("document_type", config.default_content_type),
            )
        )
        document_type = str(
            frontmatter_metadata.get(
                "document_type",
                frontmatter_metadata.get("content_type", config.default_content_type),
            )
        )
        metadata: Dict[str, Any] = {
            "dataset": config.name,
            "legal_system": config.legal_system,
            "content_type": content_type,
            "document_type": document_type,
            "title": title,
            "language": language,
            "source_path": relative_path,
            "source_file": file_path.name,
            "source_hash": source_hash,
        }
        metadata.update(frontmatter_metadata)
        return self._normalize_metadata(metadata)

    @staticmethod
    def _first_h1(markdown_body: str) -> Optional[str]:
        match = re.search(r"(?m)^#\s+(.+?)\s*$", markdown_body)
        return match.group(1).strip() if match else None

    @staticmethod
    def _header_path(metadata: Dict[str, Any]) -> str:
        return " > ".join(
            str(metadata[key]).strip()
            for key in ("header_1", "header_2", "header_3", "header_4")
            if metadata.get(key)
        )

    @staticmethod
    def _deepest_header(metadata: Dict[str, Any]) -> str:
        for key in ("header_4", "header_3", "header_2", "header_1"):
            if metadata.get(key):
                return str(metadata[key]).strip()
        return ""

    @staticmethod
    def _detect_language(text: str) -> str:
        sample = text[:5000]
        arabic_script = len(re.findall(r"[\u0600-\u06FF]", sample))
        latin_script = len(re.findall(r"[A-Za-z]", sample))
        if arabic_script and latin_script:
            ratio = arabic_script / max(arabic_script + latin_script, 1)
            if 0.25 <= ratio <= 0.75:
                return "multilingual"
            return "urdu_or_arabic" if ratio > 0.75 else "english"
        if arabic_script:
            return "urdu_or_arabic"
        return "english"

    def _build_searchable_passage(self, body: str, metadata: Dict[str, Any]) -> str:
        context_parts = []
        for label, key in (
            ("Title", "title"),
            ("Topic", "topic"),
            ("Jurisdiction", "jurisdiction"),
            ("Province", "province"),
            ("Court", "court"),
            ("Fiqh school", "school"),
            ("Section", "section"),
            ("Heading", "header_path"),
        ):
            value = metadata.get(key)
            if value not in (None, "", "N/A"):
                context_parts.append(f"{label}: {value}")
        context = "\n".join(context_parts)
        passage = f"{context}\n\n{body.strip()}" if context else body.strip()
        return passage if passage.lower().startswith(E5_PASSAGE_PREFIX) else E5_PASSAGE_PREFIX + passage

    @staticmethod
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

    @staticmethod
    def vector_id(dataset: DatasetName, source_path: str, chunk_index: int) -> str:
        digest = hashlib.sha256(f"{dataset}|{source_path}|{chunk_index}".encode("utf-8")).hexdigest()[:32]
        return f"{dataset}-{digest}"

    def ingest_dataset(
        self,
        dataset: DatasetName,
        *,
        force: bool = False,
        dry_run: bool = False,
        delete_missing: bool = True,
    ) -> Dict[str, int]:
        config = self.datasets[dataset]
        files = self.discover_files(config)
        index = self.pc.Index(config.index_name)
        discovered_paths = {path.relative_to(self.project_root).as_posix() for path in files}
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
                source_hash = hashlib.sha256(file_path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()
                old_record = self.manifest.get_source(dataset, relative_path)
                if (
                    not force
                    and old_record
                    and old_record.get("source_hash") == source_hash
                    and old_record.get("index_name") == config.index_name
                    and old_record.get("namespace") == config.namespace
                ):
                    logger.info("[%s/%s] Unchanged, skipping: %s", file_number, len(files), relative_path)
                    stats["files_skipped"] += 1
                    continue

                prepared = self.prepare_file(config, file_path)
                vector_ids = [
                    self.vector_id(dataset, prepared.source_path, i)
                    for i in range(len(prepared.chunks))
                ]
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

                old_ids = list(old_record.get("vector_ids", [])) if old_record else []
                for start in range(0, len(prepared.chunks), self.upsert_batch_size):
                    batch_docs = prepared.chunks[start:start + self.upsert_batch_size]
                    batch_ids = vector_ids[start:start + self.upsert_batch_size]
                    texts = [doc.page_content for doc in batch_docs]
                    vectors = self.embeddings.embed_documents(texts)
                    records = []
                    for vector_id, vector, document in zip(batch_ids, vectors, batch_docs):
                        metadata = {
                            **self._normalize_metadata(document.metadata),
                            self.text_key: document.page_content,
                        }
                        records.append({"id": vector_id, "values": vector, "metadata": metadata})
                    index.upsert(namespace=config.namespace, vectors=records)
                    logger.info(
                        "Upserted %s/%s chunks for %s",
                        min(start + len(batch_docs), len(prepared.chunks)),
                        len(prepared.chunks),
                        relative_path,
                    )
                    if self.upsert_pause_seconds > 0:
                        time.sleep(self.upsert_pause_seconds)

                stale_ids = sorted(set(old_ids) - set(vector_ids))
                if stale_ids:
                    self._delete_ids_in_batches(index, config.namespace, stale_ids)
                    stats["vectors_deleted"] += len(stale_ids)

                self.manifest.set_source(
                    dataset,
                    relative_path,
                    prepared.source_hash,
                    vector_ids,
                    config.index_name,
                    config.namespace,
                )
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
                if record.get("index_name") != config.index_name or record.get("namespace") != config.namespace:
                    continue
                stale_ids = list(record.get("vector_ids", []))
                if stale_ids:
                    logger.info("Deleting %s vectors for removed source %s", len(stale_ids), old_source_path)
                    self._delete_ids_in_batches(index, config.namespace, stale_ids)
                    stats["vectors_deleted"] += len(stale_ids)
                self.manifest.remove_source(dataset, old_source_path)
                self.manifest.save()

        return stats

    @staticmethod
    def _delete_ids_in_batches(index: Any, namespace: str, vector_ids: List[str], batch_size: int = 900) -> None:
        for start in range(0, len(vector_ids), batch_size):
            index.delete(namespace=namespace, ids=vector_ids[start:start + batch_size])

    def clear_dataset(self, dataset: DatasetName) -> None:
        config = self.datasets[dataset]
        logger.warning("Deleting all vectors from %s/%s", config.index_name, config.namespace)
        self.pc.Index(config.index_name).delete(namespace=config.namespace, delete_all=True)
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
    ) -> Dict[str, Dict[str, int]]:
        self.ensure_indexes(datasets)
        results: Dict[str, Dict[str, int]] = {}
        for dataset in datasets:
            if clear_first and not dry_run:
                self.clear_dataset(dataset)
            config = self.datasets[dataset]
            logger.info("=" * 72)
            logger.info("DATASET: %s", dataset.upper())
            logger.info("Source: %s", config.source_dir)
            logger.info("Index: %s | Namespace: %s", config.index_name, config.namespace)
            results[dataset] = self.ingest_dataset(
                dataset,
                force=force,
                dry_run=dry_run,
                delete_missing=delete_missing,
            )
        return results


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
    """Index an uploaded Markdown document without blocking the HTTP request."""
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
                raise ValueError(
                    "law_type must be Pakistani, Islamic, or Procedure."
                )
            if source.suffix.lower() not in {".md", ".markdown"}:
                raise ValueError(
                    "The ingestion pipeline accepts Markdown files (.md) only."
                )

            update_task(status="preparing", progress=10)
            pipeline = PropertyMarkdownIngestionPipeline()
            config = pipeline.datasets[dataset]
            config.source_dir.mkdir(parents=True, exist_ok=True)

            destination = config.source_dir / Path(original_name).name
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)

            update_task(status="indexing", progress=35)
            pipeline.ensure_indexes([dataset])
            result = pipeline.ingest_dataset(
                dataset,
                force=True,
                delete_missing=False,
            )
            if result["files_failed"]:
                raise RuntimeError(
                    f"{result['files_failed']} document(s) failed to ingest."
                )
            update_task(status="completed", progress=100, result=result)
        except Exception as exc:
            logger.exception("Upload ingestion task %s failed", task_id)
            update_task(status="failed", progress=100, error=str(exc))
        finally:
            try:
                if source.exists() and (
                    destination is None
                    or source.resolve() != destination.resolve()
                ):
                    source.unlink()
            except OSError:
                logger.warning("Could not remove temporary upload %s", source)

    thread = threading.Thread(
        target=worker,
        name=f"ingestion-{task_id}",
        daemon=True,
    )
    thread.start()
    return thread


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest Pakistani, Islamic, and procedure Markdown into Pinecone."
    )
    parser.add_argument("--dataset", choices=["all", "pakistani", "islamic", "procedure"], default="all")
    parser.add_argument("--force", action="store_true", help="Reprocess unchanged files.")
    parser.add_argument("--dry-run", action="store_true", help="Chunk without uploading.")
    parser.add_argument("--keep-missing", action="store_true", help="Do not delete vectors for removed files.")
    parser.add_argument("--clear-first", action="store_true", help="Delete selected namespaces before ingestion.")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    selected: List[DatasetName] = (
        ["pakistani", "islamic", "procedure"] if args.dataset == "all" else [args.dataset]
    )
    try:
        pipeline = PropertyMarkdownIngestionPipeline()
        results = pipeline.run(
            selected,
            force=args.force,
            dry_run=args.dry_run,
            delete_missing=not args.keep_missing,
            clear_first=args.clear_first,
        )
    except Exception as exc:
        logger.exception("Ingestion failed: %s", exc)
        return 1
    print("\nINGESTION SUMMARY")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
