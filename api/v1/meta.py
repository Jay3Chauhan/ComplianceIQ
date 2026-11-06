"""Static configuration the frontend needs: categories, modes, limits, suggestions."""

from fastapi import APIRouter, Query

from config import settings

router = APIRouter(tags=["Meta"])

APP_VERSION = "2.0.0"

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

SUGGESTIONS = {
    "RBI": [
        "What are the periodic KYC update timelines for different risk categories?",
        "What must a Key Fact Statement contain for digital loans?",
        "Can a digital lending app access the borrower's contact list?",
        "What is Video-based Customer Identification Process (V-CIP)?",
    ],
    "SEBI": [
        "What is swing pricing for mutual fund schemes?",
        "What are the total expense ratio limits for mutual fund schemes?",
        "How should stock brokers settle running accounts of clients?",
        "What are the norms for margin trading facility offered by stock brokers?",
    ],
    "AA": [
        "What is the minimum net owned fund required for an NBFC-AA?",
        "What details must a consent artefact contain?",
        "What is the role of a Financial Information Provider?",
        "Can an Account Aggregator store customer financial information?",
    ],
}


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
        },
        "features": {
            "verification": settings.enable_verification,
            "llm_verifier": settings.enable_llm_verifier,
            "answer_repair": settings.enable_answer_repair,
            "query_rewrite": settings.enable_query_rewrite,
            "rerank": settings.enable_rerank,
            "retrieval_strategy": settings.retrieval_strategy,
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
    if category == "ALL":
        pool = [q for qs in zip(*SUGGESTIONS.values()) for q in qs]
    else:
        pool = SUGGESTIONS[category]
    return {"category": category, "suggestions": pool[:limit]}
