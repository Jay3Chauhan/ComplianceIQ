"""Pydantic models for the legacy /api endpoints (used by the Streamlit UI)."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="The compliance question")
    category: Literal["ALL", "RBI", "SEBI", "AA"] | None = Field(default="ALL")
    top_k: int | None = Field(default=6, ge=1, le=10)
    history: list[dict] | None = Field(default=None, max_length=10)
    answer_mode: Literal["auto", "regulatory", "general"] | None = Field(
        default="auto",
        description="auto: cited when documents match, else general; regulatory: cited or not-found; "
        "general: no retrieval",
    )


class SourceDocument(BaseModel):
    id: int | None = None
    doc_name: str
    circular_id: str
    category: str
    section: str = ""
    page_number: int
    date: str
    source_url: str
    snippet: str
    relevance_score: float
    citation: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDocument]
    chunks_used: int
    usage: dict
    mode: str = "regulatory"
    latency_ms: int = 0
    confidence: str | None = None
    verification: dict | None = None
    revised: bool = False


class IngestRequest(BaseModel):
    filename: str = Field(..., description="Filename in data/documents/ folder")


class IngestResponse(BaseModel):
    status: str
    doc_name: str
    pages: int
    chunks: int
    vectors_stored: int


class DocumentInfo(BaseModel):
    doc_name: str
    circular_id: str
    category: str
    date: str
    issuer: str
    source_url: str


class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    collection_name: str
    total_vectors: int
    model: str
    rerank_enabled: bool = False
