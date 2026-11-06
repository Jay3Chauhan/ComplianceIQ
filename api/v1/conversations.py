"""Conversation history CRUD (scoped to X-User-Id)."""

import asyncio

from fastapi import APIRouter, Depends, Query

from api.errors import APIError
from api.schemas import Conversation, ConversationCreate, ConversationDetail, ConversationList, ConversationUpdate
from api.security import get_user_id
from db import repository as repo

router = APIRouter(prefix="/conversations", tags=["Conversations"])


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
    conv = await asyncio.to_thread(repo.get_conversation, user_id, conversation_id)
    if not conv:
        raise APIError(404, "conversation_not_found", "Conversation not found.")
    return conv


@router.patch("/{conversation_id}", response_model=Conversation)
async def update_conversation(conversation_id: str, body: ConversationUpdate,
                              user_id: str = Depends(get_user_id)) -> dict:
    conv = await asyncio.to_thread(
        repo.update_conversation, user_id, conversation_id, **body.model_dump(exclude_none=True)
    )
    if not conv:
        raise APIError(404, "conversation_not_found", "Conversation not found.")
    return conv


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, user_id: str = Depends(get_user_id)) -> None:
    if not await asyncio.to_thread(repo.delete_conversation, user_id, conversation_id):
        raise APIError(404, "conversation_not_found", "Conversation not found.")


@router.delete("", status_code=200)
async def delete_all_conversations(user_id: str = Depends(get_user_id)) -> dict:
    """Deletes every conversation for the current user."""
    return {"deleted": await asyncio.to_thread(repo.delete_all_conversations, user_id)}
