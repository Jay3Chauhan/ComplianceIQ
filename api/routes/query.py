"""POST /api/query — main RAG endpoint."""

from fastapi import APIRouter, HTTPException
from loguru import logger
from api.models import QueryRequest, QueryResponse
from retrieval.retriever import retrieve_chunks
from llm.groq_client import generate_answer

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_regulations(req: QueryRequest) -> QueryResponse:
    """
    Ask a compliance question. Returns a grounded answer with citations.

    - Retrieves top-k relevant chunks from Qdrant
    - Passes context + question to Groq LLaMA-3.3-70B
    - Returns answer with exact document citations
    """
    logger.info(f"Query received: '{req.question[:80]}...' | category={req.category}")

    try:
        chunks = retrieve_chunks(
            query=req.question,
            top_k=req.top_k,
            category_filter=req.category,
        )

        if not chunks:
            return QueryResponse(
                answer=(
                    "I could not find relevant information in the loaded regulatory documents "
                    "for your question. Please check if the relevant documents have been ingested, "
                    "or consult the regulator's official website."
                ),
                sources=[],
                chunks_used=0,
                usage={},
            )

        result = generate_answer(
            question=req.question,
            chunks=chunks,
            history=req.history,
        )

        return QueryResponse(**result)

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
