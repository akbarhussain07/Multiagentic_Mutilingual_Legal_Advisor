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
from typing import Any, Dict, List, Literal, Optional, Sequence, TypedDict

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct, SparseVector

from . import rag_config
from .diversity import order_breadth_first
from .embedder import BGEEmbedder
from .qdrant_setup import COLLECTION_NAME, get_qdrant_client, setup_collection
from .reranker import BGEReranker
from .retriever import HybridRetriever

logger = logging.getLogger(__name__)

AgentName = Literal["pakistani_agent", "islamic_agent"]
ViewMode = Literal["pakistani", "islamic", "both"]
_VALID_AGENTS: tuple[str, ...] = ("pakistani_agent", "islamic_agent")
_AGENT_ALIASES = {
    "pakistani_agent": "pakistani_agent",
    "pakistani": "pakistani_agent",
    "pakistan": "pakistani_agent",
    "pk": "pakistani_agent",
    "islamic_agent": "islamic_agent",
    "islamic": "islamic_agent",
    "islam": "islamic_agent",
    "is": "islamic_agent",
}


def _normalize_agent_name(value: Any) -> Optional[AgentName]:
    if not isinstance(value, str):
        return None
    key = re.sub(r"[^a-z_]+", "", value.strip().lower().replace("-", "_").replace(" ", "_"))
    mapped = _AGENT_ALIASES.get(key)
    if mapped in _VALID_AGENTS:
        return mapped  # type: ignore[return-value]
    return None


def _normalize_agent_list(value: Any) -> List[AgentName]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    normalized: List[AgentName] = []
    for item in value:
        agent = _normalize_agent_name(item)
        if agent and agent not in normalized:
            normalized.append(agent)
    return normalized


def _normalize_sub_query_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: Dict[str, str] = {}
    for raw_key, raw_query in value.items():
        query = str(raw_query or "").strip()
        if not query:
            continue
        agent = _normalize_agent_name(str(raw_key))
        key = agent or str(raw_key).strip().lower()
        if key:
            cleaned[key] = query
    return cleaned


_DOMAIN_HINTS = (
    "hudood", "hadd", "zina", "qisas", "diyat", "fiqh", "quran", "hadith",
    "sharia", "shariah", "islamic", "islam", "ppc", "crpc", "pakistan",
    "constitution", "assembly", "bail", "inheritance", "hiba", "waqf",
    "nikah", "talaq", "muta", "ordinance", "penal", "murder", "theft",
    "property", "land", "court", "law", "legal", "section", "article",
    "qanun", "statute", "judgment", "wasiyyah", "succession", "mutation",
    "registration", "tenant", "mortgage", "partition", "narcotic",
    "terrorism", "offence", "offense", "punishment", "witness",
    "قانون", "حدود", "زنا", "قصاص", "دیات", "شریعت", "میراث", "وراثت",
    "نکاح", "طلاق", "وقف", "ہبہ", "ضمانت", "عدالت", "شريعة", "ميراث",
)


def _looks_domain_related(question: str) -> bool:
    text = (question or "").strip().lower()
    if not text:
        return False
    if any(hint in text for hint in _DOMAIN_HINTS):
        return True
    # Arabic/Urdu legal characters often appear without Latin keywords.
    return bool(re.search(r"[\u0600-\u06FF]", question or ""))


def _looks_clearly_out_of_domain(question: str) -> bool:
    text = re.sub(r"\s+", " ", (question or "").strip().lower())
    if not text:
        return True
    if _looks_domain_related(text):
        return False
    off_topic = (
        "capital of france", "iphone", "docker", "kubernetes", "football",
        "cricket score", "weather", "recipe", "movie", "bitcoin price",
        "stock market tip", "write python code", "javascript",
    )
    return any(item in text for item in off_topic)


def _assign_sub_queries(
    raw: Dict[str, str],
    allowed: Sequence[AgentName],
    standalone: str,
) -> Dict[str, str]:
    assigned: Dict[str, str] = {}
    leftovers: List[str] = []
    for key, query in (raw or {}).items():
        text = (query or "").strip()
        if not text:
            continue
        agent = _normalize_agent_name(key)
        if agent and agent in allowed:
            assigned[agent] = text
        else:
            leftovers.append(text)
    fill = leftovers[0] if leftovers else standalone
    for agent in allowed:
        if agent not in assigned:
            assigned[agent] = fill
    return assigned


def _build_chat_model():
    """Build the chat LLM from env (Groq or OpenRouter)."""
    provider = rag_config.LLM_PROVIDER
    temperature = rag_config.GROQ_TEMPERATURE
    timeout = rag_config.GROQ_TIMEOUT_SECONDS
    max_retries = rag_config.GROQ_MAX_RETRIES

    if provider == "openrouter":
        if not rag_config.OPENROUTER_API_KEY:
            raise RuntimeError("Missing environment variable: OPENROUTER_API_KEY")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-openai is required for OpenRouter. "
                "Install with: pip install langchain-openai"
            ) from exc
        return ChatOpenAI(
            model=rag_config.OPENROUTER_MODEL,
            api_key=rag_config.OPENROUTER_API_KEY,
            base_url=rag_config.OPENROUTER_BASE_URL,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("Missing environment variable: GROQ_API_KEY")
    return ChatGroq(
        model=rag_config.GROQ_MODEL,
        temperature=temperature,
        max_retries=max_retries,
        timeout=timeout,
    )


class MasterDecision(BaseModel):
    in_scope: bool = Field(
        description=(
            "True only when the query belongs to the selected dashboard domain "
            "(Pakistani, Islamic, or Both). False for greetings already handled "
            "elsewhere and for out-of-domain questions."
        )
    )
    query_class: Literal["GREETING", "DOMAIN_QUERY", "OUT_OF_DOMAIN", "AMBIGUOUS"] = Field(
        default="DOMAIN_QUERY",
        description="Internal classification of the user message.",
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
    memory_reason: str = Field(description="Why memory is safe or unsafe to reuse.")
    selected_agents: List[str] = Field(
        default_factory=list,
        description="Only pakistani_agent and/or islamic_agent.",
    )
    sub_queries: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Retrieval queries keyed ONLY by pakistani_agent and/or islamic_agent. "
            "Never use keys such as main, query, or general."
        ),
    )
    routing_reason: str = ""

    @field_validator("selected_agents", mode="before")
    @classmethod
    def coerce_selected_agents(cls, value: Any) -> List[str]:
        return list(_normalize_agent_list(value))

    @field_validator("sub_queries", mode="before")
    @classmethod
    def coerce_sub_queries(cls, value: Any) -> Dict[str, str]:
        return _normalize_sub_query_map(value)

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
    doc_id: str


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
    merged_evidence: List[EvidenceItem]
    answer_payload: Dict[str, Any]
    answer_from_memory: bool
    error: str


MASTER_SYSTEM_PROMPT = """
You are the Master Agent for a Pakistani and Islamic law RAG system.

Dashboard selection (view_mode) is AUTHORITATIVE and must never be silently changed:
- Pakistani → Pakistani knowledge only
- Islamic → Islamic knowledge only
- Both → Pakistani and Islamic knowledge may both be used

Do NOT answer the user's legal question. Do NOT invent facts, citations, or sources.

Classify every message as one of:
GREETING | DOMAIN_QUERY | OUT_OF_DOMAIN | AMBIGUOUS

in_scope rules relative to the selected dashboard domain:
- Pakistani selected: in_scope=true only for Pakistani-law questions (statutes,
  Constitution, legislation, courts, procedure, case law, institutions, PPC/CrPC,
  registration, mutation, tenancy, succession, and related Pakistani legal topics).
- Islamic selected: in_scope=true only for Islamic questions (Quran, Hadith, fiqh,
  Sharia, Islamic inheritance, hiba, wasiyyah, waqf, and related Islamic topics).
- Both selected: in_scope=true for Pakistani and/or Islamic questions.
- Greetings/small talk: query_class=GREETING, in_scope=false.
- Unrelated topics (e.g. capital of France, Docker, iPhone price): 
  query_class=OUT_OF_DOMAIN, in_scope=false.
- Ambiguous: if it can reasonably be answered inside the selected domain, treat as
  DOMAIN_QUERY with in_scope=true; otherwise OUT_OF_DOMAIN with in_scope=false.

MEMORY DECISION (first):
Reuse a memory candidate only when ALL are true:
- Same legal issue and materially equivalent facts
- Compatible jurisdiction/province and view_mode
- Candidate ID is present in the supplied list
- Not merely topically similar
If reusable: memory_hit=true, set exact memory_id, selected_agents=[], sub_queries={{}}.

RETRIEVAL WHEN MEMORY MISSES:
Code enforces which agents run from view_mode. Your job is to:
1. Set in_scope and query_class correctly.
2. Write standalone_question with history references resolved.
3. Write a short topic.
4. Produce optimized sub_queries using ONLY these exact keys:
   - "pakistani_agent"
   - "islamic_agent"
   Example for Pakistani domain:
   sub_queries = {{"pakistani_agent": "who can dissolve National Assembly Pakistan"}}
   Never use keys like "main", "query", "general", or free-form labels.
5. Never suggest searching the other domain when only one is selected.
6. There is no procedure agent; Pakistani procedure uses pakistani_agent.
"""


ANSWER_SYSTEM_PROMPT = """
You synthesize the final answer from retrieved Qdrant evidence only.

Never invent a source title, section, page, case name, court, fiqh school, URL,
verse, hadith reference, document ID, or source ID that is not in the evidence.

Requirements:
1. Cite legal claims only with supplied IDs such as [PK-ab12] or [IS-ab12].
2. Keep Pakistani-law and Islamic-law analysis separate. Never present Islamic
   material as Pakistani law or Pakistani law as an Islamic ruling.
3. When view_mode is Both and both sides are relevant, prefer clear sections:
   Pakistani Perspective / Islamic Perspective. If only one side is relevant,
   use that side only — do not force both.
4. Put Pakistani procedure, forums, limitation and document steps in
   pakistani_analysis (and procedure_analysis when procedural).
5. Preserve uncertainty or conflicts present in the evidence.
6. Do not calculate inheritance shares if essential heirs, debts, funeral
   expenses, or will information are missing.
7. Answer in the user's language (English, Urdu, or Arabic).
8. cited_source_ids must contain only IDs actually used from the evidence.
9. Write clean Markdown: short direct conclusion, then headings and bullets.
10. Never claim a document was retrieved unless its ID appears in the evidence.
"""


FALLBACK_SYSTEM_PROMPT = """
You are the Master Agent producing the final answer after specialized retrieval
agents returned little or no usable evidence.

You MUST still answer as if synthesizing from the selected domain agents:
- Islamic selected → write islamic_analysis and a clear direct_answer
- Pakistani selected → write pakistani_analysis and a clear direct_answer
- Both selected → write both pakistani_analysis and islamic_analysis when relevant

Critical rules:
1. Stay strictly inside the selected domain (Pakistani / Islamic / Both).
2. Never claim that the answer came from retrieved documents or Qdrant unless
   evidence IDs are provided in the prompt.
3. Never invent document IDs, fake citations, or source URLs.
4. Keep cited_source_ids empty unless evidence IDs are provided.
5. Be concise, clear, factual, and well-structured Markdown.
6. Keep Pakistani and Islamic analysis separate. Never present Islamic material
   as Pakistani statute or Pakistani statute as an Islamic ruling.
7. If a detail is uncertain, state the uncertainty; do not invent section numbers
   or verse citations.
8. Answer in the user's language (English, Urdu, or Arabic).
9. For in-domain legal questions, NEVER answer with only "I don't know."
   Provide the best domain-accurate explanation you can within the selected scope.
10. Match the style of a specialized legal agent answer: short conclusion, then
    headings/bullets for rules, application, and practical notes.
"""


class SemanticAnswerMemory:
    """Qdrant stores memory vectors; SQLite stores the full answer payload."""

    def __init__(
        self,
        client,
        embedder: BGEEmbedder,
        sqlite_path: str,
        top_k: int,
        minimum_similarity: float,
    ) -> None:
        self.client = client
        self.embedder = embedder
        self.top_k = top_k
        self.minimum_similarity = minimum_similarity
        self._db_path = Path(sqlite_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()
        self._initialize_database()

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
        return sqlite3.connect(str(self._db_path), timeout=30, check_same_thread=False)

    def search(self, question: str, view_mode: ViewMode) -> List[MemoryCandidate]:
        vector = self.embedder.embed_query(question)
        mode_values = [view_mode, "both"] if view_mode != "both" else ["both", "pakistani", "islamic"]
        query_filter = Filter(
            must=[
                FieldCondition(key="content_type", match=MatchValue(value="answer_memory")),
                Filter(
                    should=[
                        FieldCondition(key="view_mode", match=MatchValue(value=mode))
                        for mode in mode_values
                    ]
                ),
            ]
        )
        try:
            response = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector.dense,
                using="dense",
                query_filter=query_filter,
                limit=self.top_k,
                with_payload=True,
            )
        except Exception as exc:
            logger.warning("Semantic memory query failed: %s", exc)
            return []

        candidates: List[MemoryCandidate] = []
        for match in getattr(response, "points", None) or []:
            payload = match.payload or {}
            memory_id = str(payload.get("memory_id") or getattr(match, "id", ""))
            score = float(getattr(match, "score", 0.0) or 0.0)
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
                SELECT memory_id, question, standalone_question, topic, jurisdiction,
                       province, view_mode, selected_agents_json, answer_payload_json,
                       sources_json, source_fingerprint, created_at
                FROM answer_memory WHERE memory_id = ?
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
        memory_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        source_fingerprint = self._source_fingerprint(sources)
        with self._db_lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO answer_memory (
                    memory_id, question, standalone_question, topic, jurisdiction,
                    province, view_mode, selected_agents_json, answer_payload_json,
                    sources_json, source_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id, question, standalone_question, topic, jurisdiction,
                    province, view_mode, json.dumps(selected_agents, ensure_ascii=False),
                    json.dumps(answer_payload, ensure_ascii=False),
                    json.dumps(sources, ensure_ascii=False), source_fingerprint, created_at,
                ),
            )
            conn.commit()

        embedding = self.embedder.embed_query(standalone_question)
        try:
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"memory:{memory_id}")),
                        vector={
                            "dense": embedding.dense,
                            "sparse": SparseVector(
                                indices=embedding.sparse_indices,
                                values=embedding.sparse_values,
                            ),
                        },
                        payload={
                            "content_type": "answer_memory",
                            "memory_id": memory_id,
                            "topic": topic[:200],
                            "jurisdiction": (jurisdiction or "")[:200],
                            "province": (province or "")[:200],
                            "view_mode": view_mode,
                            "source_fingerprint": source_fingerprint,
                            "created_at": created_at,
                            "text": standalone_question,
                        },
                    )
                ],
                wait=True,
            )
        except Exception:
            with self._db_lock, self._connect() as conn:
                conn.execute("DELETE FROM answer_memory WHERE memory_id = ?", (memory_id,))
                conn.commit()
            raise
        return memory_id

    @staticmethod
    def _source_fingerprint(sources: List[Dict[str, Any]]) -> str:
        identity = [
            {
                "source_id": source.get("source_id", ""),
                "title": source.get("title", ""),
                "section": source.get("section", ""),
                "page": source.get("page", ""),
                "source_url": source.get("source_url", ""),
            }
            for source in sources
        ]
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RAGService:
    """Master + Pakistani + Islamic agents. Procedure is not an agent."""

    _instance: Optional["RAGService"] = None

    def __new__(cls) -> "RAGService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        backend_root = Path(__file__).resolve().parent.parent
        load_dotenv(backend_root / ".env")
        load_dotenv(backend_root / "env")

        self.embedder = BGEEmbedder()
        self.reranker = BGEReranker()
        self.client = get_qdrant_client()
        setup_collection(self.client)
        self.retriever = HybridRetriever(self.client, self.embedder)
        self.model = _build_chat_model()
        logger.info(
            "LLM provider=%s model=%s",
            rag_config.LLM_PROVIDER,
            rag_config.OPENROUTER_MODEL
            if rag_config.LLM_PROVIDER == "openrouter"
            else rag_config.GROQ_MODEL,
        )
        # Default tool/function structured output. Avoid json_mode for Groq:
        # Groq requires the word "json" in messages for response_format=json_object,
        # and gpt-oss may still emit soft key names like "main" which we normalize.
        self.master_model = self.model.with_structured_output(MasterDecision)
        self.answer_model = self.model.with_structured_output(AnswerPayload)
        self.memory = SemanticAnswerMemory(
            client=self.client,
            embedder=self.embedder,
            sqlite_path=rag_config.MEMORY_SQLITE_PATH,
            top_k=rag_config.MEMORY_TOP_K,
            minimum_similarity=rag_config.MEMORY_CANDIDATE_THRESHOLD,
        )
        self.graph = self._build_graph()
        self._initialized = True

    @staticmethod
    def _messages_with_json_hint(messages: List[Any]) -> List[Any]:
        """Groq json_object mode requires the word 'json' somewhere in messages."""
        hint = (
            "Return ONLY a valid JSON object that matches the required schema. "
            "Do not wrap it in markdown."
        )
        for message in messages:
            content = getattr(message, "content", None)
            if isinstance(content, str) and "json" in content.lower():
                return messages
        from langchain_core.messages import SystemMessage

        return [SystemMessage(content=hint), *messages]

    def _invoke_structured(
        self,
        model,
        schema: type[BaseModel],
        messages: List[Any],
    ) -> BaseModel:
        try:
            result = model.invoke(messages)
            if isinstance(result, schema):
                return result
            return schema.model_validate(result)
        except Exception as first_exc:
            recovered = self._parse_failed_generation(first_exc)
            if recovered is not None:
                logger.warning(
                    "Recovered %s from failed structured output: %s",
                    schema.__name__,
                    first_exc,
                )
                return schema.model_validate(recovered)

            # Retry once with explicit JSON instruction + json_mode for models
            # that reject tool schemas but accept json_object.
            message = str(first_exc).lower()
            should_retry_json = (
                "tool call validation failed" in message
                or "tool_use_failed" in message
                or "failed_generation" in message
            )
            if not should_retry_json:
                raise

            try:
                json_model = self.model.with_structured_output(schema, method="json_mode")
            except TypeError as exc:
                raise first_exc from exc

            try:
                result = json_model.invoke(self._messages_with_json_hint(messages))
                if isinstance(result, schema):
                    return result
                return schema.model_validate(result)
            except Exception as second_exc:
                recovered = self._parse_failed_generation(second_exc)
                if recovered is not None:
                    logger.warning(
                        "Recovered %s from json_mode failure: %s",
                        schema.__name__,
                        second_exc,
                    )
                    return schema.model_validate(recovered)
                raise second_exc from first_exc

    def _invoke_master_decision(self, messages: List[Any]) -> MasterDecision:
        return self._invoke_structured(self.master_model, MasterDecision, messages)  # type: ignore[return-value]

    def _invoke_answer_payload(self, messages: List[Any]) -> AnswerPayload:
        return self._invoke_structured(self.answer_model, AnswerPayload, messages)  # type: ignore[return-value]

    @staticmethod
    def _parse_failed_generation(exc: BaseException) -> Optional[Dict[str, Any]]:
        text = str(exc)
        if "failed_generation" not in text:
            return None

        candidates: List[str] = []
        for pattern in (
            r"failed_generation['\"]?\s*:\s*'(\{.*\})'\s*([,\}])",
            r'failed_generation[\'"]?\s*:\s*"(\{.*\})"\s*([,\}])',
            r"failed_generation['\"]?\s*:\s*(\{.*\})",
        ):
            match = re.search(pattern, text, flags=re.DOTALL)
            if match:
                candidates.append(match.group(1))

        for raw in candidates:
            cleaned = raw
            try:
                cleaned = bytes(raw, "utf-8").decode("unicode_escape")
            except Exception:
                cleaned = raw
            for blob in (cleaned, raw):
                try:
                    payload = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    args = payload.get("arguments")
                    if isinstance(args, dict):
                        return args
                    return payload

        args_match = re.search(
            r'"arguments"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})',
            text,
            flags=re.DOTALL,
        )
        if args_match:
            try:
                return json.loads(args_match.group(1))
            except json.JSONDecodeError:
                return None
        return None

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("master_agent", self._master_agent)
        graph.add_node("pakistani_agent", self._pakistani_agent)
        graph.add_node("islamic_agent", self._islamic_agent)
        graph.add_node("memory_response", self._memory_response)
        graph.add_node("aggregate_evidence", self._aggregate_evidence)
        graph.add_node("answer_generator", self._answer_generator)
        graph.add_node("save_memory", self._save_memory)
        graph.add_edge(START, "master_agent")
        graph.add_conditional_edges(
            "master_agent",
            self._route_after_master,
            {
                "memory_response": "memory_response",
                "pakistani_agent": "pakistani_agent",
                "islamic_agent": "islamic_agent",
                "aggregate_evidence": "aggregate_evidence",
            },
        )
        graph.add_edge("pakistani_agent", "aggregate_evidence")
        graph.add_edge("islamic_agent", "aggregate_evidence")
        graph.add_edge("aggregate_evidence", "answer_generator")
        graph.add_edge("answer_generator", "save_memory")
        graph.add_edge("save_memory", END)
        graph.add_edge("memory_response", END)
        return graph.compile()

    def _master_agent(self, state: GraphState) -> Dict[str, Any]:
        question = state["question"].strip()
        history = self._format_history(state.get("history", []))
        view_mode: ViewMode = state.get("view_mode", "both")
        memory_candidates = self.memory.search(question=question, view_mode=view_mode)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", MASTER_SYSTEM_PROMPT),
                (
                    "human",
                    "Selected dashboard domain (authoritative): {view_mode}\n\n"
                    "Conversation history:\n{history}\n\n"
                    "Latest user question:\n{question}\n\n"
                    "Semantic memory candidates:\n{candidates}\n\n"
                    "Remember: sub_queries keys must be exactly "
                    "'pakistani_agent' and/or 'islamic_agent' (never 'main').",
                ),
            ]
        )
        decision = self._invoke_master_decision(
            prompt.format_messages(
                view_mode=view_mode,
                history=history or "(none)",
                question=question,
                candidates=self._format_memory_candidates(memory_candidates) or "(none)",
            )
        )
        valid_ids = {item["memory_id"] for item in memory_candidates}
        if decision.memory_hit and decision.memory_id not in valid_ids:
            decision.memory_hit = False
            decision.memory_id = None
            decision.memory_reason = (
                "The proposed memory ID was not present in the supplied candidates."
            )

        # Prefer retrieval for dashboard domains unless the query is clearly unrelated.
        if decision.query_class != "GREETING":
            if _looks_clearly_out_of_domain(question) and not _looks_domain_related(question):
                decision.query_class = "OUT_OF_DOMAIN"
                decision.in_scope = False
            elif decision.query_class in {"OUT_OF_DOMAIN", "AMBIGUOUS"} or not decision.in_scope:
                if _looks_domain_related(question) or not _looks_clearly_out_of_domain(question):
                    decision.query_class = "DOMAIN_QUERY"
                    decision.in_scope = True
                    decision.routing_reason = (
                        (decision.routing_reason or "")
                        + " | Forced in-scope because the question fits the selected legal dashboard."
                    ).strip(" |")

        # Dashboard selection is authoritative — never switch domains.
        if view_mode == "pakistani":
            allowed: List[AgentName] = ["pakistani_agent"]
        elif view_mode == "islamic":
            allowed = ["islamic_agent"]
        else:
            allowed = ["pakistani_agent", "islamic_agent"]

        if decision.memory_hit:
            decision.selected_agents = []
            decision.sub_queries = {}
        elif not decision.in_scope or decision.query_class in {
            "GREETING",
            "OUT_OF_DOMAIN",
        }:
            decision.in_scope = False
            decision.selected_agents = []
            decision.sub_queries = {}
        else:
            decision.selected_agents = list(allowed)
            standalone = (decision.standalone_question or question).strip()
            decision.sub_queries = _assign_sub_queries(
                decision.sub_queries or {},
                allowed,
                standalone,
            )
            decision.routing_reason = (
                decision.routing_reason
                or f"Dashboard domain '{view_mode}' requires {', '.join(allowed)}."
            )

        logger.info(
            "Master decision view_mode=%s in_scope=%s class=%s agents=%s topic=%s",
            view_mode,
            decision.in_scope,
            decision.query_class,
            decision.selected_agents,
            decision.topic,
        )

        return {
            "memory_candidates": memory_candidates,
            "master_decision": decision.model_dump(),
            "selected_agents": decision.selected_agents,
        }

    def _route_after_master(self, state: GraphState) -> List[str]:
        decision = MasterDecision.model_validate(state["master_decision"])
        if decision.memory_hit:
            return ["memory_response"]
        if not decision.in_scope or not decision.selected_agents:
            return ["aggregate_evidence"]
        return list(decision.selected_agents)

    def _memory_response(self, state: GraphState) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(state["master_decision"])
        if not decision.memory_id:
            return {
                "answer_payload": AnswerPayload(
                    direct_answer="The memory candidate could not be loaded."
                ).model_dump(),
                "memory_sources": [],
                "answer_from_memory": False,
            }
        record = self.memory.get(decision.memory_id)
        if not record:
            return {
                "answer_payload": AnswerPayload(
                    direct_answer="The memory candidate no longer exists."
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

    def _pakistani_agent(self, state: GraphState) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(state["master_decision"])
        query = decision.sub_queries.get("pakistani_agent", decision.standalone_question)
        return {
            "pakistani_evidence": self._retrieve_for_agent(
                agent_name="pakistani_agent",
                query=query,
                legal_system="Pakistani",
                province=decision.province,
            )
        }

    def _islamic_agent(self, state: GraphState) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(state["master_decision"])
        query = decision.sub_queries.get("islamic_agent", decision.standalone_question)
        return {
            "islamic_evidence": self._retrieve_for_agent(
                agent_name="islamic_agent",
                query=query,
                legal_system="Islamic",
                province=None,
            )
        }

    def _retrieve_for_agent(
        self,
        *,
        agent_name: AgentName,
        query: str,
        legal_system: str,
        province: Optional[str],
    ) -> List[EvidenceItem]:
        if not (query or "").strip():
            return []
        hits = self.retriever.retrieve(
            query,
            top_k=rag_config.RETRIEVAL_TOP_K,
            legal_system=legal_system,
            province=province,
        )
        try:
            reranked = self.reranker.rerank(query, hits, top_k=rag_config.RERANK_TOP_K)
        except Exception as exc:
            logger.warning(
                "Reranker failed for %s (%s); using retrieval ranking.",
                agent_name,
                exc,
            )
            reranked = [
                {**hit, "rerank_score": float(hit.get("score") or 0.0)}
                for hit in hits[: rag_config.RERANK_TOP_K]
            ]
        diverse = order_breadth_first(reranked, rag_config.MAX_CHUNKS_PER_DOC)
        evidence = [self._hit_to_evidence(item, agent_name) for item in diverse]
        logger.info(
            "%s retrieved=%s evidence=%s query=%r",
            agent_name,
            len(hits),
            len(evidence),
            (query or "")[:120],
        )
        return evidence

    def _hit_to_evidence(self, hit: Dict[str, Any], agent_name: AgentName) -> EvidenceItem:
        payload = dict(hit.get("payload") or {})
        digest_basis = "|".join(
            [
                agent_name,
                str(hit.get("title") or ""),
                str(hit.get("section") or ""),
                str(hit.get("page") or ""),
                (hit.get("text") or "")[:300],
            ]
        )
        digest = hashlib.sha1(digest_basis.encode("utf-8")).hexdigest()[:10]
        prefix = "PK" if agent_name == "pakistani_agent" else "IS"
        return {
            "source_id": f"{prefix}-{digest}",
            "agent": agent_name,
            "content": (hit.get("text") or "").strip(),
            "metadata": {
                **payload,
                "title": hit.get("title") or payload.get("title", "Unknown"),
                "section": hit.get("section") or payload.get("section", "N/A"),
                "page": hit.get("page") or payload.get("page_number", "N/A"),
                "source_path": hit.get("source_path") or payload.get("source_path", ""),
                "legal_system": hit.get("legal_system") or payload.get("legal_system", ""),
            },
            "retrieval_score": float(hit.get("score") or 0.0),
            "rerank_score": float(hit.get("rerank_score") or hit.get("score") or 0.0),
            "doc_id": str(hit.get("doc_id") or payload.get("doc_id") or ""),
        }

    def _aggregate_evidence(self, state: GraphState) -> Dict[str, Any]:
        combined = list(state.get("pakistani_evidence", []) or []) + list(
            state.get("islamic_evidence", []) or []
        )
        seen: set[str] = set()
        unique: List[EvidenceItem] = []
        for item in combined:
            normalized = re.sub(r"\s+", " ", item["content"]).strip().lower()
            key = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        unique.sort(key=lambda item: (item["rerank_score"], item["retrieval_score"]), reverse=True)
        as_dicts = [
            {
                **item,
                "doc_id": item.get("doc_id") or item["metadata"].get("doc_id") or item["source_id"],
            }
            for item in unique
        ]
        ordered = order_breadth_first(as_dicts, rag_config.MAX_CHUNKS_PER_DOC)
        return {"merged_evidence": ordered[: rag_config.RAG_MAX_TOTAL_EVIDENCE]}

    def _answer_generator(self, state: GraphState) -> Dict[str, Any]:
        decision = MasterDecision.model_validate(state["master_decision"])
        view_mode: ViewMode = state.get("view_mode", "both")
        question = decision.standalone_question or state.get("question", "")

        if decision.query_class == "GREETING":
            payload = AnswerPayload(direct_answer="Hello! How can I help you with your legal question?")
            return {"answer_payload": payload.model_dump(), "answer_from_memory": False}

        if (
            not decision.in_scope
            or decision.query_class == "OUT_OF_DOMAIN"
        ) and _looks_clearly_out_of_domain(question):
            payload = AnswerPayload(direct_answer="I don't know.")
            return {"answer_payload": payload.model_dump(), "answer_from_memory": False}

        # If master misfires but the question is legal, continue with domain answer.
        if not decision.in_scope:
            decision.in_scope = True
            decision.query_class = "DOMAIN_QUERY"

        evidence = list(state.get("merged_evidence", []) or [])
        logger.info(
            "Answer generator evidence=%s sufficient=%s view_mode=%s",
            len(evidence),
            self._evidence_is_sufficient(evidence),
            view_mode,
        )
        if self._evidence_is_sufficient(evidence):
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", ANSWER_SYSTEM_PROMPT),
                    (
                        "human",
                        "Selected dashboard domain: {view_mode}\n\n"
                        "Question:\n{question}\n\n"
                        "Topic: {topic}\n"
                        "Jurisdiction: {jurisdiction}\n"
                        "Province: {province}\n"
                        "Selected agents: {agents}\n\n"
                        "Evidence:\n{evidence}",
                    ),
                ]
            )
            payload = self._invoke_answer_payload(
                prompt.format_messages(
                    view_mode=view_mode,
                    question=decision.standalone_question,
                    topic=decision.topic,
                    jurisdiction=decision.jurisdiction or "Not established",
                    province=decision.province or "Not established",
                    agents=", ".join(decision.selected_agents),
                    evidence=self._format_evidence(evidence),
                )
            )
            valid_ids = {item["source_id"] for item in evidence}
            payload.cited_source_ids = [
                source_id
                for source_id in payload.cited_source_ids
                if source_id in valid_ids
            ]
            return {"answer_payload": payload.model_dump(), "answer_from_memory": False}

        # Controlled domain fallback — still answer like the specialized agents.
        domain_label = {
            "pakistani": "Pakistani law only",
            "islamic": "Islamic law / fiqh only",
            "both": "Pakistani and/or Islamic law only",
        }.get(view_mode, "Pakistani and/or Islamic law only")
        weak_evidence = self._format_evidence(evidence) if evidence else "(none)"
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", FALLBACK_SYSTEM_PROMPT),
                (
                    "human",
                    "Selected dashboard domain: {view_mode}\n"
                    "Allowed scope: {domain_label}\n"
                    "Selected agents: {agents}\n\n"
                    "Question:\n{question}\n\n"
                    "Topic: {topic}\n"
                    "Jurisdiction: {jurisdiction}\n"
                    "Province: {province}\n\n"
                    "Retrieved agent evidence was empty or too weak to ground citations.\n"
                    "Weak/partial evidence (may be empty):\n{evidence}\n\n"
                    "Produce a full domain answer in the style of the selected agent(s). "
                    "Do NOT reply with only 'I don't know.' "
                    "Fill islamic_analysis when Islamic is selected/both, and "
                    "pakistani_analysis when Pakistani is selected/both.",
                ),
            ]
        )
        payload = self._invoke_answer_payload(
            prompt.format_messages(
                view_mode=view_mode,
                domain_label=domain_label,
                agents=", ".join(decision.selected_agents) or view_mode,
                question=decision.standalone_question,
                topic=decision.topic,
                jurisdiction=decision.jurisdiction or "Not established",
                province=decision.province or "Not established",
                evidence=weak_evidence,
            )
        )
        payload.cited_source_ids = []
        if (payload.direct_answer or "").strip().lower() in {"i don't know.", "i don't know"}:
            # Hard guard: never return bare refusal for in-domain legal questions.
            if view_mode == "islamic":
                payload.direct_answer = (
                    "I can discuss this under Islamic law/fiqh, but the indexed sources "
                    "did not return a strong enough excerpt for citation. "
                    "Please rephrase with more detail (for example: Hudood, zina, "
                    "qisas, inheritance, or a specific ordinance)."
                )
                payload.islamic_analysis = payload.islamic_analysis or payload.direct_answer
            elif view_mode == "pakistani":
                payload.direct_answer = (
                    "I can discuss this under Pakistani law, but the indexed sources "
                    "did not return a strong enough excerpt for citation. "
                    "Please rephrase with a statute, section, or concrete legal issue."
                )
                payload.pakistani_analysis = payload.pakistani_analysis or payload.direct_answer
            else:
                payload.direct_answer = (
                    "I can discuss this under Pakistani and/or Islamic law, but the "
                    "indexed sources did not return a strong enough excerpt for citation. "
                    "Please add more detail about the legal issue."
                )
        return {"answer_payload": payload.model_dump(), "answer_from_memory": False}

    @staticmethod
    def _evidence_is_sufficient(evidence: List[EvidenceItem]) -> bool:
        if not evidence:
            return False
        # BGE reranker scores are often negative logits; do not require score > 0.
        substantive = [
            item
            for item in evidence
            if len((item.get("content") or "").strip()) >= 40
        ]
        return bool(substantive)

    def _save_memory(self, state: GraphState) -> Dict[str, Any]:
        if state.get("answer_from_memory"):
            return {}
        decision = MasterDecision.model_validate(state["master_decision"])
        payload = state.get("answer_payload")
        evidence = state.get("merged_evidence", [])
        if not decision.in_scope or not payload or not evidence:
            return {}
        sources = self._sources_from_evidence(evidence, payload.get("cited_source_ids", []))
        try:
            memory_id = self.memory.save(
                question=state["question"],
                standalone_question=decision.standalone_question,
                topic=decision.topic,
                jurisdiction=decision.jurisdiction or "",
                province=decision.province or "",
                view_mode=state.get("view_mode", "both"),
                selected_agents=decision.selected_agents,
                answer_payload=payload,
                sources=sources,
            )
            logger.info("Saved answer memory record: %s", memory_id)
        except Exception as exc:
            logger.exception("Unable to save answer memory: %s", exc)
        return {}

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
        if view_mode not in {"pakistani", "islamic", "both"}:
            return {
                "answer": "view_mode must be 'pakistani', 'islamic', or 'both'.",
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
            logger.exception("Legal RAG graph failed: %s", exc)
            return {
                "answer": "The legal retrieval pipeline failed to complete.",
                "error": str(exc),
                "success": False,
                "sources": [],
                "selected_agents": [],
                "from_memory": False,
            }

        payload = AnswerPayload.model_validate(output["answer_payload"])
        from_memory = bool(output.get("answer_from_memory", False))
        if from_memory:
            sources = output.get("memory_sources", [])
        else:
            sources = self._sources_from_evidence(
                output.get("merged_evidence", []),
                payload.cited_source_ids,
            )
        decision = MasterDecision.model_validate(output["master_decision"])
        return {
            "answer": payload.direct_answer,
            "pakistanContent": payload.pakistani_analysis,
            "islamicContent": payload.islamic_analysis,
            "procedureContent": payload.procedure_analysis,
            "practicalSteps": payload.practical_steps,
            "missingInformation": payload.missing_information,
            "disclaimer": payload.disclaimer,
            "sources": sources,
            "selected_agents": output.get("selected_agents", []),
            "master_decision": output.get("master_decision", {}),
            "from_memory": from_memory,
            "memory_id": decision.memory_id if from_memory else None,
            "success": True,
        }

    def check_connection(self) -> Dict[str, Any]:
        from .qdrant_setup import check_qdrant_health

        health = check_qdrant_health(self.client)
        health.update(
            {
                "configured_agents": ["master_agent", "pakistani_agent", "islamic_agent"],
                "expected_agents": ["master_agent", "pakistani_agent", "islamic_agent"],
                "memory_enabled": True,
                "memory_database": str(self.memory._db_path),
                "graph_nodes": [
                    "master_agent",
                    "pakistani_agent",
                    "islamic_agent",
                    "memory_response",
                    "aggregate_evidence",
                    "answer_generator",
                    "save_memory",
                ],
            }
        )
        return health

    @staticmethod
    def _format_history(history: List[Any]) -> str:
        lines: List[str] = []
        for item in history[-8:]:
            if isinstance(item, str):
                lines.append(item)
            elif isinstance(item, dict):
                lines.append(f"{item.get('role', 'unknown')}: {item.get('content', '')}")
            else:
                lines.append(str(item))
        return "\n".join(lines)

    @staticmethod
    def _format_memory_candidates(candidates: List[MemoryCandidate]) -> str:
        blocks = []
        for candidate in candidates:
            payload = candidate["answer_payload"]
            blocks.append(
                "\n".join(
                    [
                        f"Memory ID: {candidate['memory_id']}",
                        f"Similarity: {candidate['similarity_score']:.4f}",
                        f"Question: {candidate['question']}",
                        f"Standalone question: {candidate['standalone_question']}",
                        f"Topic: {candidate['topic']}",
                        f"View mode: {candidate['view_mode']}",
                        f"Previous direct answer: {payload.get('direct_answer', '')}",
                    ]
                )
            )
        return "\n\n---\n\n".join(blocks)

    @staticmethod
    def _format_evidence(evidence: List[EvidenceItem]) -> str:
        blocks = []
        for item in evidence:
            metadata = item["metadata"]
            blocks.append(
                "\n".join(
                    [
                        f"[{item['source_id']}]",
                        f"Agent: {item['agent']}",
                        f"Title: {metadata.get('title', 'Unknown')}",
                        f"Legal system: {metadata.get('legal_system', 'Unknown')}",
                        f"Section: {metadata.get('section', 'N/A')}",
                        f"Page: {metadata.get('page', 'N/A')}",
                        f"Source path: {metadata.get('source_path', 'N/A')}",
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
        sources = []
        for item in evidence:
            legal_system = item["metadata"].get("legal_system") or (
                "Pakistani" if item["agent"] == "pakistani_agent" else "Islamic"
            )
            sources.append(
                {
                    "source_id": item["source_id"],
                    "agent": item["agent"],
                    "law_type": legal_system,
                    "title": item["metadata"].get("title", "Unknown"),
                    "section": item["metadata"].get("section", "N/A"),
                    "page": item["metadata"].get("page", "N/A"),
                    "source_path": item["metadata"].get("source_path", ""),
                    "content": item["content"],
                    "retrieval_score": item["retrieval_score"],
                    "rerank_score": item["rerank_score"],
                    "cited": item["source_id"] in cited,
                }
            )
        return sources
