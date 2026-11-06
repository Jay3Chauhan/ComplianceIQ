"""Static configuration the frontend needs: categories, modes, limits, suggestions."""

from fastapi import APIRouter, Query

from config import settings
from rag.suggestions import starter_questions

router = APIRouter(tags=["Meta"])

APP_VERSION = "2.1.0"

CATEGORIES = [
    {"id": "ALL", "label": "All regulators", "description": "Search every loaded document"},
    {"id": "RBI", "label": "RBI", "description": "Reserve Bank of India master directions and circulars"},
    {"id": "SEBI", "label": "SEBI", "description": "SEBI master circulars"},
    {"id": "AA", "label": "Account Aggregator", "description": "RBI NBFC-AA directions and ReBIT specifications"},
]

ANSWER_MODES = [
    {"id": "auto", "label": "Auto",
     "description": "Cited answer when the documents cover it, otherwise a clearly-labelled general answer"},
    {"id": "regulatory", "label": "Documents only",
     "description": "Only answers from loaded documents; says so when they don't cover the question"},
    {"id": "general", "label": "General knowledge",
     "description": "Answers from general finance knowledge without document citations"},
]


@router.get("/meta")
async def meta() -> dict:
    return {
        "version": APP_VERSION,
        "categories": CATEGORIES,
        "answer_modes": ANSWER_MODES,
        "limits": {
            "question_max_chars": 2000,
            "top_k_max": 10,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
            "max_upload_mb": settings.max_upload_mb,
            "sse_heartbeat_seconds": settings.sse_heartbeat_seconds,
        },
        "features": {
            "verification": settings.enable_verification,
            "llm_verifier": settings.enable_llm_verifier,
            "answer_repair": settings.enable_answer_repair,
            "query_rewrite": settings.enable_query_rewrite,
            "rerank": settings.enable_rerank,
            "retrieval_strategy": settings.retrieval_strategy,
            "followups": settings.enable_followups,
            "llm_titles": settings.enable_llm_titles,
            "stop": True,
            "regenerate": True,
            "edit": True,
            "export_formats": ["markdown", "json"],
        },
        "models": {
            "answer": settings.groq_model,
            "fallback": settings.fallback_model_list,
            "fast": settings.groq_fast_model,
            "embedding": settings.embedding_model,
            "reranker": settings.reranker_model if settings.enable_rerank else None,
        },
    }


@router.get("/suggestions")
async def suggestions(category: str = Query("ALL", pattern="^(ALL|RBI|SEBI|AA)$"), limit: int = Query(4, ge=1, le=12)) -> dict:
    return {"category": category, "suggestions": starter_questions(category, limit)}
