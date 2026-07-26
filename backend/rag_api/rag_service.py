from __future__ import annotations
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import Pinecone as PineconeVectorStore
from langgraph.graph import END, START, StateGraph
from pinecone import Pinecone as PineconeClient, ServerlessSpec
from pydantic import BaseModel, Field, field_validator
logger = logging.getLogger(__name__)

AgentName = Literal["pakistani_agent", "islamic_agent", "procedure_agent"]
ViewMode = Literal["pakistani", "islamic", "procedure"]

# Structured model outputs

class MasterDecision(BaseModel):
    """
    Decision produced by the Master Agent after it has inspected semantic
    memory candidates.

    The Master Agent is one of the four agents. Memory search is an internal
    capability of this agent, not a fifth agent.
    """

    in_scope: bool = Field(
        description="True only for Pakistani or Islamic property-law questions."
    )
    standalone_question: str = Field(
        description="Complete question with references resolved from chat history."
    )
    topic: str = Field(
        description="Short normalized topic such as mutation, hiba, inheritance."
    )
    jurisdiction: Optional[str] = None
    province: Optional[str] = None

    memory_hit: bool = Field(
        description=(
            "True only when one supplied memory candidate answers the same legal "
            "question with materially equivalent facts and matching jurisdiction."
        )
    )
    memory_id: Optional[str] = Field(
        default=None,
        description="Exact memory candidate ID to reuse when memory_hit is true.",
    )
    memory_reason: str = Field(
        description="Why memory is safe or unsafe to reuse."
    )

    selected_agents: List[AgentName] = Field(default_factory=list)
    sub_queries: Dict[AgentName, str] = Field(default_factory=dict)
    routing_reason: str = ""

    @field_validator("selected_agents")
    @classmethod
    def unique_agents(cls, value: List[AgentName]) -> List[AgentName]:
        return list(dict.fromkeys(value))


class AnswerPayload(BaseModel):
    direct_answer: str
    pakistani_analysis: str = ""
    islamic_analysis: str = ""
    procedure_analysis: str = ""
    practical_steps: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    cited_source_ids: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "This is source-based legal information, not a substitute for advice "
        "from a qualified Pakistani lawyer or qualified Islamic scholar."
    )


class EvidenceItem(TypedDict):
    source_id: str
    agent: str
    content: str
    metadata: Dict[str, Any]
    retrieval_score: float
    rerank_score: float


class MemoryCandidate(TypedDict):
    memory_id: str
    question: str
    standalone_question: str
    topic: str
    jurisdiction: str
    province: str
    view_mode: str
    selected_agents: List[str]
    answer_payload: Dict[str, Any]
    sources: List[Dict[str, Any]]
    source_fingerprint: str
    created_at: str
    similarity_score: float


class GraphState(TypedDict, total=False):
    question: str
    history: List[Any]
    view_mode: ViewMode

    memory_candidates: List[MemoryCandidate]
    master_decision: Dict[str, Any]
    selected_agents: List[AgentName]

    memory_answer_payload: Dict[str, Any]
    memory_sources: List[Dict[str, Any]]

    pakistani_evidence: List[EvidenceItem]
    islamic_evidence: List[EvidenceItem]
    procedure_evidence: List[EvidenceItem]
    merged_evidence: List[EvidenceItem]

    answer_payload: Dict[str, Any]
    answer_from_memory: bool
    error: str


MASTER_SYSTEM_PROMPT = """
You are the Master Agent for a Pakistani and Islamic PROPERTY-LAW RAG system.

You have two responsibilities, in this exact order:

A. MEMORY DECISION
You receive zero or more previous-answer memory candidates.
Reuse a memory answer only when ALL of these are true:
- It addresses the same legal issue.
- Material facts are equivalent.
- Jurisdiction/province is compatible.
- The requested legal framework/view mode is compatible.
- The new question does not add an important fact.
- The candidate is not merely topically similar.
- The candidate ID is actually present in the supplied candidates.

Important examples:
- "Can a father gift a house to one son?" is NOT equivalent to
  "Can a terminally ill father gift a house to one son?"
- Punjab and Sindh procedures are not automatically interchangeable.
- A general hiba answer is not automatically reusable for a disputed oral gift
  after the donor's death.
- A question asking for both Pakistani and Islamic law must not reuse an answer
  that covers only one framework.

If a candidate is safe to reuse:
- set memory_hit=true,
- provide its exact memory_id,
- selected_agents must be empty,
- sub_queries must be empty.

B. RETRIEVAL ROUTING WHEN MEMORY MISSES
Available retrieval agents:

1. pakistani_agent
   Pakistani statutes and rules: ownership, title, sale, transfer,
   registration, mutation, tenancy, land records, succession procedure,
   stamp matters, mortgage, possession, partition and acquisition.

2. islamic_agent
   Islamic inheritance, hiba, wasiyyah, waqf, Islamic sale, ijarah, rahn,
   ownership and other Sharia property-law issues.

3. procedure_agent
   Judgments, court procedure, evidence, burden of proof, remedies, forums,
   limitation, document requirements and administrative procedure.

Routing rules:
- Select only agents that are necessary.
- Generate a separate optimized retrieval query for each selected agent.
- A contested oral property gift after death commonly needs all three.
- A pure Islamic inheritance-share question may need islamic_agent only.
- Registry/mutation questions normally need pakistani_agent and may require
  procedure_agent when documents or steps are requested.
- Do not answer the user's legal question.
- Do not invent missing facts.
"""


ANSWER_SYSTEM_PROMPT = """
You are the final synthesis step, not an agent.

Use only the supplied evidence. Never invent a source title, section, page,
case name, court, fiqh school, URL, verse, hadith reference, or source ID.

Requirements:
1. Cite legal claims only with supplied IDs such as [PK-ab12].
2. Keep Pakistani-law, Islamic-law and procedure/case analysis separate.
3. State clearly when evidence is insufficient or conflicting.
4. Do not merge Pakistani law and Islamic law into one rule.
5. Do not calculate inheritance shares if essential heirs, debts, funeral
   expenses, or will information are missing.
6. Answer in the user's language.
7. cited_source_ids must contain only IDs actually used.
8. Write direct_answer and each applicable analysis field as clean Markdown.
9. Start with a short direct conclusion, then use descriptive headings and
   concise bullet points for rules, application, required documents and next steps.
10. Use Markdown tables only for genuine comparisons. Use LaTeX notation only
    when a mathematical expression (such as an inheritance fraction) benefits
    from it; do not use LaTeX merely for visual decoration.
"""

# Persistent semantic answer memory

class SemanticAnswerMemory:
    """
    Pinecone stores semantic vectors and lightweight searchable metadata.
    SQLite stores the full answer payload and sources.

    This avoids placing long legal answers inside Pinecone metadata.
    """

    def __init__(
        self,
        pinecone: PineconeClient,
        embeddings: HuggingFaceEmbeddings,
        index_name: str,
        dimension: int,
        metric: str,
        cloud: str,
        region: str,
        namespace: str,
        sqlite_path: str,
        top_k: int,
        minimum_similarity: float,
        auto_create_index: bool,
    ) -> None:
        self.pc = pinecone
        self.embeddings = embeddings
        self.index_name = index_name
        self.dimension = dimension
        self.metric = metric
        self.cloud = cloud
        self.region = region
        self.namespace = namespace
        self.top_k = top_k
        self.minimum_similarity = minimum_similarity
        self.auto_create_index = auto_create_index

        self._db_path = Path(sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()

        self._initialize_database()
        self.index = self._initialize_index()

    def _initialize_database(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS answer_memory (
                    memory_id TEXT PRIMARY KEY,
                    question TEXT NOT NULL,
                    standalone_question TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    jurisdiction TEXT NOT NULL,
                    province TEXT NOT NULL,
                    view_mode TEXT NOT NULL,
                    selected_agents_json TEXT NOT NULL,
                    answer_payload_json TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(
            str(self._db_path),
            timeout=30,
            check_same_thread=False,
        )

    def _initialize_index(self):
        existing = {
            item["name"] if isinstance(item, dict) else item.name
            for item in self.pc.list_indexes()
        }

        if self.index_name not in existing:
            if not self.auto_create_index:
                logger.warning(
                    "Memory index %s does not exist; semantic memory disabled.",
                    self.index_name,
                )
                return None

            logger.info("Creating Pinecone memory index %s", self.index_name)
            self.pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric=self.metric,
                spec=ServerlessSpec(
                    cloud=self.cloud,
                    region=self.region,
                ),
            )

        return self.pc.Index(self.index_name)

    def search(
        self,
        question: str,
        view_mode: ViewMode,
    ) -> List[MemoryCandidate]:
        if not self.index:
            return []

        vector = self.embeddings.embed_query(f"query: {question}")

        # The Master Agent performs the final safety decision. This filter only
        # removes clearly incompatible modes.
        mode_filter: Dict[str, Any]
        if view_mode == "both":
            mode_filter = {"view_mode": {"$eq": "both"}}
        else:
            mode_filter = {
                "view_mode": {
                    "$in": [view_mode, "both"]
                }
            }

        try:
            response = self.index.query(
                namespace=self.namespace,
                vector=vector,
                top_k=self.top_k,
                include_metadata=True,
                filter=mode_filter,
            )
        except Exception as exc:
            logger.warning("Semantic memory query failed: %s", exc)
            return []

        matches = getattr(response, "matches", None)
        if matches is None and isinstance(response, dict):
            matches = response.get("matches", [])
        matches = matches or []

        candidates: List[MemoryCandidate] = []

        for match in matches:
            if isinstance(match, dict):
                memory_id = str(match.get("id", ""))
                score = float(match.get("score", 0.0))
            else:
                memory_id = str(getattr(match, "id", ""))
                score = float(getattr(match, "score", 0.0))

            if not memory_id or score < self.minimum_similarity:
                continue

            record = self.get(memory_id)
            if not record:
                continue

            record["similarity_score"] = score
            candidates.append(record)

        return candidates

    def get(self, memory_id: str) -> Optional[MemoryCandidate]:
        with self._db_lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    memory_id,
                    question,
                    standalone_question,
                    topic,
                    jurisdiction,
                    province,
                    view_mode,
                    selected_agents_json,
                    answer_payload_json,
                    sources_json,
                    source_fingerprint,
                    created_at
                FROM answer_memory
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()

        if not row:
            return None

        return {
            "memory_id": row[0],
            "question": row[1],
            "standalone_question": row[2],
            "topic": row[3],
            "jurisdiction": row[4],
            "province": row[5],
            "view_mode": row[6],
            "selected_agents": json.loads(row[7]),
            "answer_payload": json.loads(row[8]),
            "sources": json.loads(row[9]),
            "source_fingerprint": row[10],
            "created_at": row[11],
            "similarity_score": 0.0,
        }

    def save(
        self,
        *,
        question: str,
        standalone_question: str,
        topic: str,
        jurisdiction: str,
        province: str,
        view_mode: ViewMode,
        selected_agents: List[str],
        answer_payload: Dict[str, Any],
        sources: List[Dict[str, Any]],
    ) -> Optional[str]:
        if not self.index:
            return None

        memory_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        source_fingerprint = self._source_fingerprint(sources)

        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO answer_memory (
                    memory_id,
                    question,
                    standalone_question,
                    topic,
                    jurisdiction,
                    province,
                    view_mode,
                    selected_agents_json,
                    answer_payload_json,
                    sources_json,
                    source_fingerprint,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    question,
                    standalone_question,
                    topic,
                    jurisdiction,
                    province,
                    view_mode,
                    json.dumps(selected_agents, ensure_ascii=False),
                    json.dumps(answer_payload, ensure_ascii=False),
                    json.dumps(sources, ensure_ascii=False),
                    source_fingerprint,
                    created_at,
                ),
            )
            conn.commit()

        vector = self.embeddings.embed_query(
            f"query: {standalone_question}"
        )

        metadata = {
            "topic": topic[:200],
            "jurisdiction": jurisdiction[:200],
            "province": province[:200],
            "view_mode": view_mode,
            "source_fingerprint": source_fingerprint,
            "created_at": created_at,
        }

        try:
            self.index.upsert(
                namespace=self.namespace,
                vectors=[
                    {
                        "id": memory_id,
                        "values": vector,
                        "metadata": metadata,
                    }
                ],
            )
        except Exception:
            # Keep the two stores consistent.
            with self._db_lock, self._connect() as conn:
                conn.execute(
                    "DELETE FROM answer_memory WHERE memory_id = ?",
                    (memory_id,),
                )
                conn.commit()
            raise

        return memory_id

    @staticmethod
    def _source_fingerprint(
        sources: List[Dict[str, Any]],
    ) -> str:
        identity = [
            {
                "source_id": source.get("source_id", ""),
                "title": source.get("title", ""),
                "section": source.get("section", ""),
                "page": source.get("page", ""),
                "source_url": source.get("source_url", ""),
                "updated_at": source.get("updated_at", ""),
            }
            for source in sources
        ]
        canonical = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# Three specialized retrieval agents

class BaseRetrievalAgent:
    def __init__(
        self,
        *,
        agent_name: AgentName,
        vectorstore: PineconeVectorStore,
        embeddings: HuggingFaceEmbeddings,
        fetch_k: int,
        final_k: int,
        score_threshold: float,
    ) -> None:
        self.agent_name = agent_name
        self.vectorstore = vectorstore
        self.embeddings = embeddings
        self.fetch_k = fetch_k
        self.final_k = final_k
        self.score_threshold = score_threshold

    def retrieve(
        self,
        query: str,
        decision: MasterDecision,
    ) -> List[EvidenceItem]:
        if not query.strip():
            return []

        prefixed = (
            query if query.lower().startswith("query:")
            else f"query: {query}"
        )
        metadata_filter = self.build_filter(decision)

        try:
            raw = self.vectorstore.similarity_search_with_relevance_scores(
                query=prefixed,
                k=self.fetch_k,
                filter=metadata_filter,
            )
        except Exception as exc:
            logger.warning(
                "%s filtered search failed (%s); retrying unfiltered.",
                self.agent_name,
                exc,
            )
            raw = self.vectorstore.similarity_search_with_relevance_scores(
                query=prefixed,
                k=self.fetch_k,
            )

        items = self._normalize(raw)
        items = self._deduplicate(items)
        items = self._rerank(query, items)
        return items[: self.final_k]

    def build_filter(
        self,
        decision: MasterDecision,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def _normalize(
        self,
        raw: List[Any],
    ) -> List[EvidenceItem]:
        items: List[EvidenceItem] = []

        for result in raw:
            if isinstance(result, tuple) and len(result) == 2:
                document, score = result
            else:
                document, score = result, 0.0

            if not isinstance(document, Document):
                continue

            try:
                relevance = float(score)
            except (TypeError, ValueError):
                relevance = 0.0

            if relevance and relevance < self.score_threshold:
                continue

            metadata = dict(document.metadata or {})
            digest_basis = "|".join(
                [
                    self.agent_name,
                    str(metadata.get("title", "")),
                    str(metadata.get("section", "")),
                    str(metadata.get("page", "")),
                    document.page_content[:300],
                ]
            )
            digest = hashlib.sha1(
                digest_basis.encode("utf-8")
            ).hexdigest()[:10]

            prefix = {
                "pakistani_agent": "PK",
                "islamic_agent": "IS",
                "procedure_agent": "PR",
            }[self.agent_name]

            items.append(
                {
                    "source_id": f"{prefix}-{digest}",
                    "agent": self.agent_name,
                    "content": document.page_content.strip(),
                    "metadata": metadata,
                    "retrieval_score": relevance,
                    "rerank_score": 0.0,
                }
            )

        return items

    @staticmethod
    def _deduplicate(
        items: List[EvidenceItem],
    ) -> List[EvidenceItem]:
        seen: set[str] = set()
        output: List[EvidenceItem] = []

        for item in items:
            normalized = re.sub(
                r"\s+",
                " ",
                item["content"],
            ).strip().lower()
            key = hashlib.sha1(normalized.encode("utf-8")).hexdigest()

            if key in seen:
                continue

            seen.add(key)
            output.append(item)

        return output

    def _rerank(
        self,
        query: str,
        items: List[EvidenceItem],
    ) -> List[EvidenceItem]:
        if not items:
            return []

        try:
            query_vector = self.embeddings.embed_query(
                f"query: {query}"
            )
            document_vectors = self.embeddings.embed_documents(
                [
                    item["content"]
                    if item["content"].lower().startswith("passage:")
                    else f"passage: {item['content']}"
                    for item in items
                ]
            )

            for item, vector in zip(items, document_vectors):
                item["rerank_score"] = float(
                    sum(a * b for a, b in zip(query_vector, vector))
                )
        except Exception as exc:
            logger.warning(
                "%s local reranking failed: %s",
                self.agent_name,
                exc,
            )
            for item in items:
                item["rerank_score"] = item["retrieval_score"]

        return sorted(
            items,
            key=lambda item: (
                item["rerank_score"],
                item["retrieval_score"],
            ),
            reverse=True,
        )


class PakistaniRetrievalAgent(BaseRetrievalAgent):
    def build_filter(
        self,
        decision: MasterDecision,
    ) -> Dict[str, Any]:
        clauses: List[Dict[str, Any]] = [
            {"legal_system": {"$eq": "Pakistani"}}
        ]

        if decision.province:
            clauses.append(
                {
                    "$or": [
                        {"province": {"$eq": decision.province}},
                        {"jurisdiction": {"$eq": "Pakistan"}},
                        {"jurisdiction": {"$eq": "Federal"}},
                    ]
                }
            )

        return (
            clauses[0]
            if len(clauses) == 1
            else {"$and": clauses}
        )


class IslamicRetrievalAgent(BaseRetrievalAgent):
    def build_filter(
        self,
        decision: MasterDecision,
    ) -> Dict[str, Any]:
        return {"legal_system": {"$eq": "Islamic"}}


class ProcedureRetrievalAgent(BaseRetrievalAgent):
    def build_filter(
        self,
        decision: MasterDecision,
    ) -> Dict[str, Any]:
        clauses: List[Dict[str, Any]] = [
            {
                "content_type": {
                    "$in": [
                        "case_law",
                        "judgment",
                        "procedure",
                        "document_checklist",
                        "official_guideline",
                    ]
                }
            }
        ]

        if decision.province:
            clauses.append(
                {
                    "$or": [
                        {"province": {"$eq": decision.province}},
                        {"jurisdiction": {"$eq": "Pakistan"}},
                        {"jurisdiction": {"$eq": "Federal"}},
                    ]
                }
            )

        return (
            clauses[0]
            if len(clauses) == 1
            else {"$and": clauses}
        )


# Main service and graph

class RAGService:
    """
    Exactly four agents:

    1. master_agent
       - rewrites the question,
       - checks semantic answer memory,
       - validates a possible memory hit,
       - routes on a miss.

    2. pakistani_agent
    3. islamic_agent
    4. procedure_agent

    The aggregator, answer generator, memory response, and memory save nodes
    are deterministic processing nodes, not agents.
    """

    _instance: Optional["RAGService"] = None

    def __new__(cls) -> "RAGService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        load_dotenv()
        self._validate_environment()

        self.fetch_k = int(os.getenv("RAG_FETCH_K", "8"))
        self.final_k = int(
            os.getenv("RAG_FINAL_K_PER_AGENT", "4")
        )
        self.max_total_evidence = int(
            os.getenv("RAG_MAX_TOTAL_EVIDENCE", "10")
        )
        self.score_threshold = float(
            os.getenv("RAG_SCORE_THRESHOLD", "0.20")
        )

        self.embeddings = HuggingFaceEmbeddings(
            model_name=os.getenv(
                "EMBEDDING_MODEL",
                "intfloat/multilingual-e5-large",
            ),
            model_kwargs={
                "device": os.getenv("EMBEDDING_DEVICE", "cpu")
            },
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": int(
                    os.getenv("EMBEDDING_BATCH_SIZE", "16")
                ),
            },
        )

        self.model = ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=float(
                os.getenv("GROQ_TEMPERATURE", "0.1")
            ),
            max_retries=int(
                os.getenv("GROQ_MAX_RETRIES", "2")
            ),
            timeout=float(
                os.getenv("GROQ_TIMEOUT_SECONDS", "60")
            ),
        )

        self.master_model = self.model.with_structured_output(
            MasterDecision
        )
        self.answer_model = self.model.with_structured_output(
            AnswerPayload
        )

        self.pc = PineconeClient(
            api_key=os.environ["PINECONE_API_KEY"]
        )
        self.vectorstores = self._build_vectorstores()
        self.retrieval_agents = self._build_retrieval_agents()

        self.memory = SemanticAnswerMemory(
            pinecone=self.pc,
            embeddings=self.embeddings,
            index_name=os.getenv(
                "PINECONE_MEMORY_INDEX",
                "property-answer-memory",
            ),
            dimension=int(
                os.getenv("EMBEDDING_DIMENSION", "1024")
            ),
            metric=os.getenv("PINECONE_METRIC", "cosine"),
            cloud=os.getenv("PINECONE_CLOUD", "aws"),
            region=os.getenv(
                "PINECONE_REGION",
                "us-east-1",
            ),
            namespace=os.getenv(
                "PINECONE_MEMORY_NAMESPACE",
                "answers",
            ),
            sqlite_path=os.getenv(
                "MEMORY_SQLITE_PATH",
                "./data/property_answer_memory.sqlite3",
            ),
            top_k=int(os.getenv("MEMORY_TOP_K", "3")),
            minimum_similarity=float(
                os.getenv(
                    "MEMORY_CANDIDATE_THRESHOLD",
                    "0.84",
                )
            ),
            auto_create_index=(
                os.getenv(
                    "MEMORY_AUTO_CREATE_INDEX",
                    "true",
                ).lower()
                == "true"
            ),
        )

        self.graph = self._build_graph()
        self._initialized = True

    @staticmethod
    def _validate_environment() -> None:
        required = [
            "GROQ_API_KEY",
            "PINECONE_API_KEY",
        ]
        missing = [
            name for name in required if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "Missing environment variables: "
                + ", ".join(missing)
            )

    def _build_vectorstores(
        self,
    ) -> Dict[AgentName, PineconeVectorStore]:
        text_key = os.getenv("PINECONE_TEXT_KEY", "text")
        indexes: Dict[AgentName, str] = {
            "pakistani_agent": os.getenv(
                "PINECONE_PAKISTANI_INDEX",
                "pakistani-property-law",
            ),
            "islamic_agent": os.getenv(
                "PINECONE_ISLAMIC_INDEX",
                "islamic-property-law",
            ),
            "procedure_agent": os.getenv(
                "PINECONE_PROCEDURE_INDEX",
                "property-case-procedure",
            ),
        }

        stores: Dict[AgentName, PineconeVectorStore] = {}

        for agent_name, index_name in indexes.items():
            try:
                stores[agent_name] = PineconeVectorStore(
                    index=self.pc.Index(index_name),
                    embedding=self.embeddings,
                    text_key=text_key,
                    namespace=os.getenv(
                        {
                            "pakistani_agent":
                                "PINECONE_PAKISTANI_NAMESPACE",
                            "islamic_agent":
                                "PINECONE_ISLAMIC_NAMESPACE",
                            "procedure_agent":
                                "PINECONE_PROCEDURE_NAMESPACE",
                        }[agent_name]
                    )
                    or "documents",
                )
            except Exception as exc:
                logger.exception(
                    "Unable to configure %s index %s: %s",
                    agent_name,
                    index_name,
                    exc,
                )

        return stores

    def _build_retrieval_agents(
        self,
    ) -> Dict[AgentName, BaseRetrievalAgent]:
        agents: Dict[AgentName, BaseRetrievalAgent] = {}

        if "pakistani_agent" in self.vectorstores:
            agents["pakistani_agent"] = (
                PakistaniRetrievalAgent(
                    agent_name="pakistani_agent",
                    vectorstore=self.vectorstores[
                        "pakistani_agent"
                    ],
                    embeddings=self.embeddings,
                    fetch_k=self.fetch_k,
                    final_k=self.final_k,
                    score_threshold=self.score_threshold,
                )
            )

        if "islamic_agent" in self.vectorstores:
            agents["islamic_agent"] = IslamicRetrievalAgent(
                agent_name="islamic_agent",
                vectorstore=self.vectorstores[
                    "islamic_agent"
                ],
                embeddings=self.embeddings,
                fetch_k=self.fetch_k,
                final_k=self.final_k,
                score_threshold=self.score_threshold,
            )

        if "procedure_agent" in self.vectorstores:
            agents["procedure_agent"] = (
                ProcedureRetrievalAgent(
                    agent_name="procedure_agent",
                    vectorstore=self.vectorstores[
                        "procedure_agent"
                    ],
                    embeddings=self.embeddings,
                    fetch_k=self.fetch_k,
                    final_k=self.final_k,
                    score_threshold=self.score_threshold,
                )
            )

        return agents

    def _build_graph(self):
        graph = StateGraph(GraphState)

        # Exactly four agent nodes.
        graph.add_node("master_agent", self._master_agent)
        graph.add_node(
            "pakistani_agent",
            self._pakistani_agent,
        )
        graph.add_node(
            "islamic_agent",
            self._islamic_agent,
        )
        graph.add_node(
            "procedure_agent",
            self._procedure_agent,
        )

        # Non-agent processing nodes.
        graph.add_node(
            "memory_response",
            self._memory_response,
        )
        graph.add_node(
            "aggregate_evidence",
            self._aggregate_evidence,
        )
        graph.add_node(
            "answer_generator",
            self._answer_generator,
        )
        graph.add_node(
            "save_memory",
            self._save_memory,
        )

        graph.add_edge(START, "master_agent")

        graph.add_conditional_edges(
            "master_agent",
            self._route_after_master,
            {
                "memory_response": "memory_response",
                "pakistani_agent": "pakistani_agent",
                "islamic_agent": "islamic_agent",
                "procedure_agent": "procedure_agent",
                "aggregate_evidence": "aggregate_evidence",
            },
        )

        graph.add_edge(
            "pakistani_agent",
            "aggregate_evidence",
        )
        graph.add_edge(
            "islamic_agent",
            "aggregate_evidence",
        )
        graph.add_edge(
            "procedure_agent",
            "aggregate_evidence",
        )

        graph.add_edge(
            "aggregate_evidence",
            "answer_generator",
        )
        graph.add_edge(
            "answer_generator",
            "save_memory",
        )
        graph.add_edge("save_memory", END)
        graph.add_edge("memory_response", END)

        return graph.compile()

    # Master Agent: memory check + routing

    def _master_agent(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        question = state["question"].strip()
        history = self._format_history(
            state.get("history", [])
        )
        view_mode: ViewMode = state.get(
            "view_mode",
            "both",
        )

        # First perform semantic memory search.
        memory_candidates = self.memory.search(
            question=question,
            view_mode=view_mode,
        )

        candidate_text = self._format_memory_candidates(
            memory_candidates
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", MASTER_SYSTEM_PROMPT),
                (
                    "human",
                    "View mode: {view_mode}\n\n"
                    "Conversation history:\n{history}\n\n"
                    "Latest user question:\n{question}\n\n"
                    "Semantic memory candidates:\n{candidates}",
                ),
            ]
        )

        decision = self.master_model.invoke(
            prompt.format_messages(
                view_mode=view_mode,
                history=history or "(none)",
                question=question,
                candidates=candidate_text or "(none)",
            )
        )

        valid_candidate_ids = {
            item["memory_id"]
            for item in memory_candidates
        }

        # Never trust an invented memory ID.
        if (
            decision.memory_hit
            and decision.memory_id not in valid_candidate_ids
        ):
            decision.memory_hit = False
            decision.memory_id = None
            decision.memory_reason = (
                "The proposed memory ID was not present in "
                "the supplied candidates."
            )

        allowed: set[AgentName]
        if view_mode == "pakistani":
            allowed = {"pakistani_agent"}
        elif view_mode == "islamic":
            allowed = {"islamic_agent"}
        else:
            allowed = {"procedure_agent"}

        if decision.memory_hit:
            decision.selected_agents = []
            decision.sub_queries = {}
        else:
            decision.selected_agents = [
                agent
                for agent in decision.selected_agents
                if (
                    agent in allowed
                    and agent in self.retrieval_agents
                )
            ]
            decision.sub_queries = {
                agent: query
                for agent, query in decision.sub_queries.items()
                if (
                    agent in decision.selected_agents
                    and query.strip()
                )
            }

            if (
                decision.in_scope
                and not decision.selected_agents
            ):
                fallback: List[AgentName]
                fallback = [{
                    "pakistani": "pakistani_agent",
                    "islamic": "islamic_agent",
                    "procedure": "procedure_agent",
                }[view_mode]]

                decision.selected_agents = [
                    agent
                    for agent in fallback
                    if agent in self.retrieval_agents
                ]
                for agent in decision.selected_agents:
                    decision.sub_queries[agent] = (
                        decision.standalone_question
                    )

        return {
            "memory_candidates": memory_candidates,
            "master_decision": decision.model_dump(),
            "selected_agents": decision.selected_agents,
        }

    def _route_after_master(
        self,
        state: GraphState,
    ) -> List[str]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )

        if decision.memory_hit:
            return ["memory_response"]

        if (
            not decision.in_scope
            or not decision.selected_agents
        ):
            return ["aggregate_evidence"]

        # LangGraph fans out to one, two, or all three selected agents.
        return list(decision.selected_agents)

    def _memory_response(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )

        if not decision.memory_id:
            return {
                "answer_payload": AnswerPayload(
                    direct_answer=(
                        "The memory candidate could not be loaded."
                    )
                ).model_dump(),
                "memory_sources": [],
                "answer_from_memory": False,
            }

        record = self.memory.get(decision.memory_id)

        if not record:
            return {
                "answer_payload": AnswerPayload(
                    direct_answer=(
                        "The memory candidate no longer exists."
                    )
                ).model_dump(),
                "memory_sources": [],
                "answer_from_memory": False,
            }

        return {
            "memory_answer_payload": record["answer_payload"],
            "answer_payload": record["answer_payload"],
            "memory_sources": record["sources"],
            "answer_from_memory": True,
        }

    # Three retrieval agents

    def _pakistani_agent(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )
        agent = self.retrieval_agents.get(
            "pakistani_agent"
        )

        if not agent:
            return {"pakistani_evidence": []}

        query = decision.sub_queries.get(
            "pakistani_agent",
            decision.standalone_question,
        )
        return {
            "pakistani_evidence": agent.retrieve(
                query,
                decision,
            )
        }

    def _islamic_agent(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )
        agent = self.retrieval_agents.get(
            "islamic_agent"
        )

        if not agent:
            return {"islamic_evidence": []}

        query = decision.sub_queries.get(
            "islamic_agent",
            decision.standalone_question,
        )
        return {
            "islamic_evidence": agent.retrieve(
                query,
                decision,
            )
        }

    def _procedure_agent(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )
        agent = self.retrieval_agents.get(
            "procedure_agent"
        )

        if not agent:
            return {"procedure_evidence": []}

        query = decision.sub_queries.get(
            "procedure_agent",
            decision.standalone_question,
        )
        return {
            "procedure_evidence": agent.retrieve(
                query,
                decision,
            )
        }

    # Non-agent processing nodes

    def _aggregate_evidence(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        combined = (
            state.get("pakistani_evidence", [])
            + state.get("islamic_evidence", [])
            + state.get("procedure_evidence", [])
        )

        seen: set[str] = set()
        unique: List[EvidenceItem] = []

        for item in combined:
            normalized = re.sub(
                r"\s+",
                " ",
                item["content"],
            ).strip().lower()
            key = hashlib.sha1(
                normalized.encode("utf-8")
            ).hexdigest()

            if key in seen:
                continue

            seen.add(key)
            unique.append(item)

        unique.sort(
            key=lambda item: (
                item["rerank_score"],
                item["retrieval_score"],
            ),
            reverse=True,
        )

        return {
            "merged_evidence":
                unique[: self.max_total_evidence]
        }

    def _answer_generator(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(
            state["master_decision"]
        )

        if not decision.in_scope:
            payload = AnswerPayload(
                direct_answer=(
                    "This system only handles Pakistani and "
                    "Islamic property-law questions."
                )
            )
            return {
                "answer_payload": payload.model_dump(),
                "answer_from_memory": False,
            }

        evidence = state.get("merged_evidence", [])

        if not evidence:
            payload = AnswerPayload(
                direct_answer=(
                    "No sufficiently relevant supporting material "
                    "was found in the configured legal indexes."
                )
            )
            return {
                "answer_payload": payload.model_dump(),
                "answer_from_memory": False,
            }

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ANSWER_SYSTEM_PROMPT),
                (
                    "human",
                    "Question:\n{question}\n\n"
                    "Topic: {topic}\n"
                    "Jurisdiction: {jurisdiction}\n"
                    "Province: {province}\n"
                    "Selected agents: {agents}\n\n"
                    "Evidence:\n{evidence}",
                ),
            ]
        )

        payload = self.answer_model.invoke(
            prompt.format_messages(
                question=decision.standalone_question,
                topic=decision.topic,
                jurisdiction=(
                    decision.jurisdiction
                    or "Not established"
                ),
                province=(
                    decision.province
                    or "Not established"
                ),
                agents=", ".join(
                    decision.selected_agents
                ),
                evidence=self._format_evidence(evidence),
            )
        )

        valid_ids = {
            item["source_id"]
            for item in evidence
        }
        payload.cited_source_ids = [
            source_id
            for source_id in payload.cited_source_ids
            if source_id in valid_ids
        ]

        return {
            "answer_payload": payload.model_dump(),
            "answer_from_memory": False,
        }

    def _save_memory(
        self,
        state: GraphState,
    ) -> Dict[str, Any]:
        if state.get("answer_from_memory"):
            return {}

        decision = MasterDecision.model_validate(
            state["master_decision"]
        )
        payload = state.get("answer_payload")
        evidence = state.get("merged_evidence", [])

        if (
            not decision.in_scope
            or not payload
            or not evidence
        ):
            return {}

        sources = self._sources_from_evidence(
            evidence,
            payload.get("cited_source_ids", []),
        )

        try:
            memory_id = self.memory.save(
                question=state["question"],
                standalone_question=(
                    decision.standalone_question
                ),
                topic=decision.topic,
                jurisdiction=(
                    decision.jurisdiction or ""
                ),
                province=decision.province or "",
                view_mode=state.get(
                    "view_mode",
                    "both",
                ),
                selected_agents=decision.selected_agents,
                answer_payload=payload,
                sources=sources,
            )
            logger.info(
                "Saved answer memory record: %s",
                memory_id,
            )
        except Exception as exc:
            # Failure to save memory must not destroy the answer.
            logger.exception(
                "Unable to save answer memory: %s",
                exc,
            )

        return {}

    # Public API

    def query(
        self,
        question: str,
        view_mode: ViewMode = "pakistani",
        chat_history: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        question = (question or "").strip()

        if not question:
            return {
                "answer": "Question is required.",
                "success": False,
                "sources": [],
                "selected_agents": [],
                "from_memory": False,
            }

        if view_mode not in {
            "pakistani",
            "islamic",
            "procedure",
        }:
            return {
                "answer": (
                    "view_mode must be 'pakistani', "
                    "'islamic', or 'procedure'."
                ),
                "success": False,
                "sources": [],
                "selected_agents": [],
                "from_memory": False,
            }

        try:
            output: GraphState = self.graph.invoke(
                {
                    "question": question,
                    "history": chat_history or [],
                    "view_mode": view_mode,
                }
            )
        except Exception as exc:
            logger.exception(
                "Property RAG graph failed: %s",
                exc,
            )
            return {
                "answer": (
                    "The property-law retrieval pipeline "
                    "failed to complete."
                ),
                "error": str(exc),
                "success": False,
                "sources": [],
                "selected_agents": [],
                "from_memory": False,
            }

        payload = AnswerPayload.model_validate(
            output["answer_payload"]
        )
        from_memory = bool(
            output.get("answer_from_memory", False)
        )

        if from_memory:
            sources = output.get("memory_sources", [])
        else:
            sources = self._sources_from_evidence(
                output.get("merged_evidence", []),
                payload.cited_source_ids,
            )

        decision = MasterDecision.model_validate(
            output["master_decision"]
        )

        return {
            "answer": payload.direct_answer,
            "pakistanContent":
                payload.pakistani_analysis,
            "islamicContent":
                payload.islamic_analysis,
            "procedureContent":
                payload.procedure_analysis,
            "practicalSteps":
                payload.practical_steps,
            "missingInformation":
                payload.missing_information,
            "disclaimer": payload.disclaimer,
            "sources": sources,
            "selected_agents":
                output.get("selected_agents", []),
            "master_decision":
                output.get("master_decision", {}),
            "from_memory": from_memory,
            "memory_id": (
                decision.memory_id
                if from_memory
                else None
            ),
            "success": True,
        }

    def check_connection(self) -> Dict[str, Any]:
        return {
            "connected": bool(self.retrieval_agents),
            "configured_agents": [
                "master_agent",
                *self.retrieval_agents.keys(),
            ],
            "expected_agents": [
                "master_agent",
                "pakistani_agent",
                "islamic_agent",
                "procedure_agent",
            ],
            "memory_enabled":
                self.memory.index is not None,
            "memory_index":
                self.memory.index_name,
            "memory_database":
                str(self.memory._db_path),
            "graph_nodes": [
                "master_agent",
                "pakistani_agent",
                "islamic_agent",
                "procedure_agent",
                "memory_response",
                "aggregate_evidence",
                "answer_generator",
                "save_memory",
            ],
        }

    def get_similar_questions(
        self,
        question: str,
        k: int = 3,
    ) -> List[str]:
        candidates = self.memory.search(
            question=question,
            view_mode="both",
        )
        return [
            item["standalone_question"]
            for item in candidates[:k]
        ]

    # Formatting helpers

    @staticmethod
    def _format_history(
        history: List[Any],
    ) -> str:
        lines: List[str] = []

        for item in history[-8:]:
            if isinstance(item, str):
                lines.append(item)
            elif isinstance(item, dict):
                lines.append(
                    f"{item.get('role', 'unknown')}: "
                    f"{item.get('content', '')}"
                )
            else:
                lines.append(str(item))

        return "\n".join(lines)

    @staticmethod
    def _format_memory_candidates(
        candidates: List[MemoryCandidate],
    ) -> str:
        blocks: List[str] = []

        for candidate in candidates:
            payload = candidate["answer_payload"]
            blocks.append(
                "\n".join(
                    [
                        f"Memory ID: {candidate['memory_id']}",
                        f"Similarity: {candidate['similarity_score']:.4f}",
                        f"Question: {candidate['question']}",
                        (
                            "Standalone question: "
                            f"{candidate['standalone_question']}"
                        ),
                        f"Topic: {candidate['topic']}",
                        (
                            "Jurisdiction: "
                            f"{candidate['jurisdiction'] or 'Unknown'}"
                        ),
                        (
                            "Province: "
                            f"{candidate['province'] or 'Unknown'}"
                        ),
                        f"View mode: {candidate['view_mode']}",
                        (
                            "Selected agents: "
                            + ", ".join(
                                candidate["selected_agents"]
                            )
                        ),
                        (
                            "Previous direct answer: "
                            f"{payload.get('direct_answer', '')}"
                        ),
                        (
                            "Created at: "
                            f"{candidate['created_at']}"
                        ),
                    ]
                )
            )

        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _format_evidence(
        evidence: List[EvidenceItem],
    ) -> str:
        blocks: List[str] = []

        for item in evidence:
            metadata = item["metadata"]
            blocks.append(
                "\n".join(
                    [
                        f"[{item['source_id']}]",
                        f"Agent: {item['agent']}",
                        (
                            "Title: "
                            f"{metadata.get('title', 'Unknown')}"
                        ),
                        (
                            "Document type: "
                            f"{metadata.get('document_type', metadata.get('content_type', 'Unknown'))}"
                        ),
                        (
                            "Jurisdiction: "
                            f"{metadata.get('jurisdiction', 'Unknown')}"
                        ),
                        (
                            "Province: "
                            f"{metadata.get('province', 'N/A')}"
                        ),
                        (
                            "Section: "
                            f"{metadata.get('section', 'N/A')}"
                        ),
                        (
                            "Page: "
                            f"{metadata.get('page', 'N/A')}"
                        ),
                        (
                            "Court: "
                            f"{metadata.get('court', 'N/A')}"
                        ),
                        (
                            "Case number: "
                            f"{metadata.get('case_number', 'N/A')}"
                        ),
                        (
                            "School: "
                            f"{metadata.get('school', 'N/A')}"
                        ),
                        (
                            "Source URL: "
                            f"{metadata.get('source_url', metadata.get('source', 'N/A'))}"
                        ),
                        "Content:",
                        item["content"],
                    ]
                )
            )

        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _sources_from_evidence(
        evidence: List[EvidenceItem],
        cited_source_ids: List[str],
    ) -> List[Dict[str, Any]]:
        cited = set(cited_source_ids)

        return [
            {
                "source_id": item["source_id"],
                "agent": item["agent"],
                "title":
                    item["metadata"].get(
                        "title",
                        "Unknown",
                    ),
                "section":
                    item["metadata"].get(
                        "section",
                        "N/A",
                    ),
                "page":
                    item["metadata"].get(
                        "page",
                        "N/A",
                    ),
                "court":
                    item["metadata"].get(
                        "court",
                        "N/A",
                    ),
                "case_number":
                    item["metadata"].get(
                        "case_number",
                        "N/A",
                    ),
                "jurisdiction":
                    item["metadata"].get(
                        "jurisdiction",
                        "Unknown",
                    ),
                "province":
                    item["metadata"].get(
                        "province",
                        "N/A",
                    ),
                "school":
                    item["metadata"].get(
                        "school",
                        "N/A",
                    ),
                "source_url":
                    item["metadata"].get(
                        "source_url",
                        item["metadata"].get(
                            "source",
                            "",
                        ),
                    ),
                "updated_at":
                    item["metadata"].get(
                        "updated_at",
                        "",
                    ),
                "content": item["content"],
                "retrieval_score":
                    item["retrieval_score"],
                "rerank_score":
                    item["rerank_score"],
                "cited":
                    item["source_id"] in cited,
            }
            for item in evidence
        ]
