"""Versioned public API (/api/v1)."""

from fastapi import APIRouter, Depends

from api.security import require_api_key
from api.v1 import admin, chat, conversations, documents, health, meta, search

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)

protected = APIRouter(dependencies=[Depends(require_api_key)])
protected.include_router(chat.router)
protected.include_router(conversations.router)
protected.include_router(search.router)
protected.include_router(documents.router)
protected.include_router(meta.router)
protected.include_router(admin.router)
router.include_router(protected)
