"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000, description="The compliance question")
    category: Optional[Literal["ALL", "RBI", "SEBI", "AA"]] = Field(
        default="ALL", description="Filter by document category"
    )
    top_k: Optional[int] = Field(default=5, ge=1, le=10, description="Number of chunks to retrieve")
    history: Optional[list[dict]] = Field(default=None, description="Previous conversation turns")


class SourceDocument(BaseModel):
    doc_name: str
    circular_id: str
    category: str
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
