"""Greetings and small-talk that must never trigger RAG."""
from __future__ import annotations

import re

_LEGAL_TERMS = (
    "property", "land", "house", "inherit", "heir", "hiba", "gift",
    "mutation", "registry", "registration", "tenant", "court", "case",
    "transfer", "sale", "ownership", "document", "limitation", "waqf",
    "section", "article", "ppc", "crpc", "penal", "bail", "qanun",
    "statute", "judgment", "constitution", "fiqh", "quran", "hadith",
    "wasiyyah", "nikah", "talaq", "law", "legal", "act",
    "قانون", "ضمانت", "میراث", "وراثت", "حصہ", "ہبہ", "وقف",
    "میراث", "شریعت", "قصاص", "حدود", "نکاح", "طلاق",
    "حكم", "ميراث", "قانون", "شريعة", "وقف", "هبة",
)

_EN_GREETING = re.compile(
    r"^(hi|hello|hey|assalam(?:u|o)?\s*(?:alaikum|alikum)?|"
    r"salam|good\s+(?:morning|evening|afternoon|night)|"
    r"thanks|thank\s+you|how\s+are\s+you|who\s+are\s+you|"
    r"what\s+can\s+you\s+(?:do|provide)|how\s+can\s+you\s+help|"
    r"what\s+do\s+you\s+do)\b",
    re.IGNORECASE,
)

_AR_UR_GREETING = re.compile(
    r"(السلام\s*عليكم|السلام\s*علیکم|وعليكم\s*السلام|وعلیکم\s*السلام|"
    r"مرحبا|شكرا|شكرًا|سلام|شکریہ|صبح\s*بخیر|شام\s*بخیر|"
    r"آداب|خوش\s*آمدید)"
)

_CAPABILITY = (
    "what can you provide", "what can you do", "how can you help",
    "who are you", "what do you do",
)


def is_smalltalk(question: str) -> bool:
    raw = (question or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if any(term in lowered or term in raw for term in _LEGAL_TERMS):
        return False
    if _AR_UR_GREETING.search(raw) and len(raw) < 80:
        return True
    latin = re.sub(r"[^a-z0-9\s']", " ", lowered)
    latin = re.sub(r"\s+", " ", latin).strip()
    if not latin:
        return False
    if any(phrase in latin for phrase in _CAPABILITY):
        return True
    if _EN_GREETING.match(latin) and len(latin) < 80:
        return True
    if re.match(r"^(i am|i'm|my name is)\s+[a-z]", latin):
        return True
    return False


def smalltalk_reply(question: str, view_mode: str) -> dict:
    raw = (question or "").strip()
    if re.search(r"السلام|سلام|assalam|salaam", raw, re.IGNORECASE) and not re.search(
        r"وعليكم|وعلیکم|wa\s*alaikum", raw, re.IGNORECASE
    ):
        greeting = "Wa Alaikum Assalam! How can I help you?"
    elif re.search(r"شكرا|شکریہ|thank", raw, re.IGNORECASE):
        greeting = "You're welcome. Ask whenever you have a legal question."
    elif re.search(r"how are you", raw, re.IGNORECASE):
        greeting = "I'm well, thank you. How can I help you with a legal question?"
    else:
        greeting = "Hello! How can I help you with your legal question?"

    mode_label = {
        "pakistani": "Pakistani law",
        "islamic": "Islamic law",
        "both": "Pakistani and Islamic law",
    }.get(view_mode, "Pakistani and Islamic law")

    answer = (
        f"## {greeting}\n\n"
        "I can help with source-based legal information in two areas:\n\n"
        "- **Pakistani:** statutes, Constitution, courts, procedure, PPC/CrPC, "
        "registration, mutation, tenancy, succession and related Pakistani legal documents.\n"
        "- **Islamic:** Quran, Hadith, fiqh, inheritance, hiba, wasiyyah, waqf "
        "and other Sharia rules.\n\n"
        f"Your current source is **{mode_label}**."
    )
    return {
        "answer": answer,
        "pakistanContent": answer if view_mode in {"pakistani", "both"} else "",
        "islamicContent": answer if view_mode in {"islamic", "both"} else "",
        "procedureContent": "",
        "sources": [],
        "selected_agents": [],
        "from_memory": False,
        "success": True,
    }
