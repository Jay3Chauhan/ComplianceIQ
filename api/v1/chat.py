"""Chat endpoints: JSON and Server-Sent Events streaming."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.errors import APIError
from api.schemas import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse
from api.security import get_user_id, rate_limit_chat
from api.services import chat as chat_service
from db import repository as repo
from llm.groq_client import LLMUnavailableError

router = APIRouter(tags=["Chat"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
async def chat(req: ChatRequest, user_id: str = Depends(get_user_id)) -> dict:
    """
    Ask a question and receive the complete, verified answer.
    Creates a conversation when `conversation_id` is omitted and `save` is true.
    """
    try:
        return await asyncio.to_thread(chat_service.run_chat, req, user_id)
    except LLMUnavailableError:
        raise APIError(503, "llm_unavailable", "The language model is rate limited. Try again in a minute.",
                       headers={"Retry-After": "30"})


@router.post(
    "/chat/stream",
    dependencies=[Depends(rate_limit_chat)],
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE stream (see docs/API.md)"}},
)
async def chat_stream(req: ChatRequest, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    """Streams status, sources, tokens, verification and the final message id as SSE."""
    conversation_id, user_msg, history = await asyncio.to_thread(chat_service.prepare_stream, req, user_id)
    return StreamingResponse(
        chat_service.stream_chat(req, user_id, conversation_id, user_msg, history),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.put("/messages/{message_id}/feedback", response_model=FeedbackResponse, tags=["Feedback"])
async def put_feedback(message_id: str, body: FeedbackRequest, user_id: str = Depends(get_user_id)) -> dict:
    """Rate an assistant answer (idempotent per user and message)."""
    result = await asyncio.to_thread(
        repo.upsert_feedback, user_id, message_id, body.rating, body.reasons, body.comment
    )
    if not result:
        raise APIError(404, "message_not_found", "Assistant message not found.")
    return result


@router.delete("/messages/{message_id}/feedback", status_code=204, tags=["Feedback"])
async def delete_feedback(message_id: str, user_id: str = Depends(get_user_id)) -> None:
    if not await asyncio.to_thread(repo.delete_feedback, user_id, message_id):
        raise APIError(404, "feedback_not_found", "No feedback to delete.")
