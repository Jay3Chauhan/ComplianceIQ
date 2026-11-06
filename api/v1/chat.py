"""Chat endpoints: ask (JSON or SSE), regenerate, edit, message lookup and feedback."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.errors import APIError
from api.schemas import (
    ChatRequest,
    ChatResponse,
    EditRequest,
    FeedbackRequest,
    FeedbackResponse,
    Message,
    RegenerateRequest,
)
from api.security import get_user_id, rate_limit_chat
from api.services import chat as chat_service
from db import repository as repo
from llm.groq_client import LLMUnavailableError

router = APIRouter(tags=["Chat"])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
SSE_RESPONSE = {200: {"content": {"text/event-stream": {}}, "description": "SSE stream (see docs/API.md)"}}


def _sse(job: chat_service.ChatJob) -> StreamingResponse:
    return StreamingResponse(chat_service.start_stream(job), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit_chat)])
async def chat(req: ChatRequest, user_id: str = Depends(get_user_id)) -> dict:
    """
    Ask a question and receive the complete, verified answer.
    Creates a conversation when `conversation_id` is omitted and `save` is true.
    """
    job = await asyncio.to_thread(chat_service.prepare_chat, req, user_id, "chat")
    try:
        return await asyncio.to_thread(chat_service.run_chat, job)
    except LLMUnavailableError:
        raise APIError(503, "llm_unavailable", "The language model is rate limited. Try again in a minute.",
                       headers={"Retry-After": "30"})


@router.post("/chat/stream", dependencies=[Depends(rate_limit_chat)], responses=SSE_RESPONSE)
async def chat_stream(req: ChatRequest, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    """Streams status, sources, tokens, verification, follow-ups and the saved message id as SSE."""
    job = await asyncio.to_thread(chat_service.prepare_chat, req, user_id, "chat_stream")
    return _sse(job)


@router.post("/messages/{message_id}/regenerate", dependencies=[Depends(rate_limit_chat)], responses=SSE_RESPONSE)
async def regenerate(message_id: str, body: RegenerateRequest | None = None,
                     user_id: str = Depends(get_user_id)) -> StreamingResponse:
    """
    Answers the question behind an assistant message again (also "retry" after an error
    or a stopped answer). The old answer and every later message are removed.
    """
    job = await asyncio.to_thread(chat_service.prepare_regenerate, user_id, message_id, body or RegenerateRequest())
    return _sse(job)


@router.post("/messages/{message_id}/edit", dependencies=[Depends(rate_limit_chat)], responses=SSE_RESPONSE)
async def edit(message_id: str, body: EditRequest, user_id: str = Depends(get_user_id)) -> StreamingResponse:
    """Replaces a question, removes every later message, and streams the new answer."""
    job = await asyncio.to_thread(chat_service.prepare_edit, user_id, message_id, body)
    return _sse(job)


@router.get("/messages/{message_id}", response_model=Message)
async def get_message(message_id: str, user_id: str = Depends(get_user_id)) -> dict:
    """One message with sources, verification, follow-ups and your feedback."""
    msg = await asyncio.to_thread(repo.get_message, user_id, message_id)
    if not msg:
        raise APIError(404, "message_not_found", "Message not found.")
    return msg


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
