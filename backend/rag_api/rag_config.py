"""Shared RAG configuration. PostgreSQL/auth settings stay in Django settings."""
from __future__ import annotations

import os

from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")
load_dotenv(_BACKEND_ROOT / "env")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal-advisor")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "40"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "15"))
MAX_CHUNKS_PER_DOC = int(os.getenv("MAX_CHUNKS_PER_DOC", "3"))
RAG_MAX_TOTAL_EVIDENCE = int(os.getenv("RAG_MAX_TOTAL_EVIDENCE", "12"))

RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_MAX_LENGTH = int(os.getenv("RERANKER_MAX_LENGTH", "1024"))

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.1"))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "60"))

# Optional OpenRouter fallback (same model IDs as OpenRouter catalog).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or None
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", GROQ_MODEL)
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

INGESTION_VERSION = os.getenv("INGESTION_VERSION", "legal-ingestion-v2")
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "512"))
CHUNK_THRESHOLD = float(os.getenv("CHUNK_THRESHOLD", "0.5"))
MIN_CHUNK_CHARS = int(os.getenv("MIN_CHUNK_CHARS", "30"))
MAX_TOKENS_PER_SEGMENT = int(os.getenv("MAX_TOKENS_PER_SEGMENT", "4000"))

MEMORY_CANDIDATE_THRESHOLD = float(os.getenv("MEMORY_CANDIDATE_THRESHOLD", "0.84"))
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "3"))
MEMORY_SQLITE_PATH = os.getenv(
    "MEMORY_SQLITE_PATH",
    "./data/property_answer_memory.sqlite3",
)

UPSERT_BATCH_SIZE = int(os.getenv("UPSERT_BATCH_SIZE", "50"))
