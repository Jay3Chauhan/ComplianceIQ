"""Conversation history CRUD, stop and export (scoped to X-User-Id)."""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.errors import APIError
from api.schemas import (
    Conversation,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationUpdate,
    StopResponse,
)
from api.security import get_user_id
from api.services import chat as chat_service
from api.services.export import export_filename, to_markdown
from api.services.runs import runs
from db import repository as repo

router = APIRouter(prefix="/conversations", tags=["Conversations"])


async def _get_or_404(user_id: str, conversation_id: str) -> dict:
    conv = await asyncio.to_thread(repo.get_conversation, user_id, conversation_id)
    if not conv:
        raise APIError(404, "conversation_not_found", "Conversation not found.")
    return conv


@router.get("", response_model=ConversationList)
async def list_conversations(
    user_id: str = Depends(get_user_id),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, max_length=200, description="Search titles and message text"),
    archived: bool = False,
) -> dict:
    items, total = await asyncio.to_thread(repo.list_conversations, user_id, limit, offset, q, archived)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=Conversation, status_code=201)
async def create_conversation(body: ConversationCreate, user_id: str = Depends(get_user_id)) -> dict:
    return await asyncio.to_thread(repo.create_conversation, user_id, body.title, body.category, body.answer_mode)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> dict:
    """Messages oldest first. `streaming` is true while an answer is still being generated."""
    conv = await _get_or_404(user_id, conversation_id)
    return {**conv, "streaming": runs.is_active(conversation_id)}


@router.patch("/{conversation_id}", response_model=Conversation)
async def update_conversation(conversation_id: str, body: ConversationUpdate,
                              user_id: str = Depends(get_user_id)) -> dict:
    conv = await asyncio.to_thread(
        repo.update_conversation, user_id, conversation_id, **body.model_dump(exclude_none=True)
    )
    if not conv:
        raise APIError(404, "conversation_not_found", "Conversation not found.")
    return conv


@router.post("/{conversation_id}/stop", response_model=StopResponse)
async def stop_generation(conversation_id: str, user_id: str = Depends(get_user_id)) -> dict:
    """
    Stops the answer being generated in this conversation. The partial answer is saved
    with status "stopped" and the open stream ends with a `done` event (status "stopped").
    """
    stopped = await asyncio.to_thread(chat_service.stop, user_id, conversation_id)
    return {"conversation_id": conversation_id, "stopped": stopped}


@router.get(
    "/{conversation_id}/export",
    responses={200: {"content": {"text/markdown": {}, "application/json": {}}}},
)
async def export_conversation(
    conversation_id: str,
    format: Literal["markdown", "json"] = Query("markdown"),
    user_id: str = Depends(get_user_id),
) -> Response:
    """Downloads the conversation with answers, verification status and full citations."""
    conv = await _get_or_404(user_id, conversation_id)
    if format == "json":
        body, media, ext = json.dumps(conv, ensure_ascii=False, indent=2), "application/json", "json"
    else:
        body, media, ext = to_markdown(conv), "text/markdown; charset=utf-8", "md"
    return Response(
        body, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{export_filename(conv, ext)}"'},
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> None:
    if runs.is_active(conversation_id):
        await asyncio.to_thread(chat_service.stop, user_id, conversation_id)
    if not await asyncio.to_thread(repo.delete_conversation, user_id, conversation_id):
        raise APIError(404, "conversation_not_found", "Conversation not found.")


@router.delete("", status_code=200)
async def delete_all_conversations(user_id: str = Depends(get_user_id)) -> dict:
    """Deletes every conversation for the current user."""
    return {"deleted": await asyncio.to_thread(repo.delete_all_conversations, user_id)}
