"""Pydantic schemas for the /api/v1 endpoints."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["ALL", "RBI", "SEBI", "AA"]
AnswerMode = Literal["auto", "regulatory", "general"]
ResponseMode = Literal["regulatory", "general", "not_found"]
MessageStatus = Literal["complete", "error", "stopped"]
Confidence = Literal["high", "medium", "low"]
VerificationStatus = Literal["verified", "partially_verified", "unverified", "not_applicable"]
FeedbackReason = Literal[
    "incorrect", "not_grounded", "missing_info", "wrong_citation", "outdated", "unclear", "too_long", "other"
]


class HistoryTurn(BaseModel):
    question: str = Field(..., max_length=2000)
    answer: str = Field("", max_length=8000)


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="The user's question")
    conversation_id: str | None = Field(None, description="Continue an existing conversation")
    category: Category = Field("ALL", description="Restrict retrieval to one regulator")
    answer_mode: AnswerMode = Field(
        "auto",
        description="auto: cited answer when documents match, otherwise general knowledge; "
        "regulatory: cited answer or explicit 'not found'; general: no retrieval",
    )
    top_k: int | None = Field(None, ge=1, le=10, description="Passages given to the model (default 6)")
    history: list[HistoryTurn] | None = Field(
        None, max_length=10, description="Stateless history; ignored when conversation_id is set"
    )
    verify: bool | None = Field(None, description="Override answer verification (default on)")
    save: bool = Field(True, description="Persist the exchange in a conversation")
    followups: bool = Field(True, description="Suggest next questions after the answer")

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _clean_question(v)


def _clean_question(v: str) -> str:
    v = v.strip()
    if len(v) < 3:
        raise ValueError("question is too short")
    return v


class RegenerateRequest(BaseModel):
    """Answer the same question again. Omitted fields reuse the conversation's settings."""
    category: Category | None = None
    answer_mode: AnswerMode | None = None
    top_k: int | None = Field(None, ge=1, le=10)
    verify: bool | None = None
    followups: bool = True


class EditRequest(RegenerateRequest):
    """Replace a question and answer it; every later message in the conversation is removed."""
    question: str = Field(..., min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _clean_question(v)


class Source(BaseModel):
    id: int = Field(..., description="Citation number used as [n] in the answer")
    chunk_id: str
    doc_id: str
    doc_name: str
    circular_id: str = ""
    category: str = ""
    section: str = ""
    page_number: int
    date: str = ""
    source_url: str = ""
    filename: str = ""
    snippet: str
    text: str
    relevance_score: float
    citation: str = ""


class UnsupportedClaim(BaseModel):
    claim: str
    reason: str = ""


class Verification(BaseModel):
    status: VerificationStatus
    score: float
    method: str
    claims_checked: int = 0
    supported: int = 0
    unsupported_claims: list[UnsupportedClaim] = []
    uncited_claims: list[str] = []
    invalid_citations: list[int] = []
    unsupported_numbers: list[str] = []
    citation_issues: list[str] = []


class ChatResponse(BaseModel):
    conversation_id: str | None
    message_id: str | None
    user_message_id: str | None
    answer: str
    mode: ResponseMode
    grounded: bool
    gate_score: float
    confidence: Confidence | None
    sources: list[Source]
    verification: Verification | None
    revised: bool
    standalone_question: str
    model: str | None
    latency_ms: int
    timings: dict
    followups: list[str] = []
    title: str | None = Field(None, description="Conversation title after this exchange")


# ── Conversations ────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    category: Category = "ALL"
    answer_mode: AnswerMode = "auto"


class ConversationUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None
    category: Category | None = None
    answer_mode: AnswerMode | None = None


class Conversation(BaseModel):
    id: str
    title: str
    category: str
    answer_mode: str
    pinned: bool
    archived: bool
    message_count: int
    created_at: str
    updated_at: str


class MessageFeedback(BaseModel):
    rating: int
    reasons: list[str] = []
    comment: str | None = None


class Message(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    status: MessageStatus
    mode: str | None = None
    followups: list[str] = []
    sources: list[Source] = []
    verification: Verification | None = None
    confidence: str | None = None
    revised: bool = False
    standalone_question: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    created_at: str
    feedback: MessageFeedback | None = None


class ConversationDetail(Conversation):
    messages: list[Message]
    streaming: bool = Field(False, description="An answer is being generated right now")


class StopResponse(BaseModel):
    conversation_id: str
    stopped: bool = Field(..., description="False when nothing was running")


class ConversationList(BaseModel):
    items: list[Conversation]
    total: int
    limit: int
    offset: int


# ── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    rating: Literal[1, -1] = Field(..., description="1 = helpful, -1 = not helpful")
    reasons: list[FeedbackReason] | None = Field(None, max_length=8)
    comment: str | None = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    message_id: str
    rating: int
    reasons: list[str]
    comment: str | None
    created_at: str


# ── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    category: Category = "ALL"
    top_k: int = Field(8, ge=1, le=20)
    rerank: bool = True


class SearchResponse(BaseModel):
    query: str
    search_query: str
    grounded: bool
    gate_score: float
    results: list[Source]
    timings: dict


# ── Documents ────────────────────────────────────────────────────────────────

class DocumentSummary(BaseModel):
    doc_id: str
    name: str
    circular_id: str
    category: str
    subcategory: str
    date: str
    issuer: str
    source_url: str
    filename: str
    has_file: bool
    chunks: int
    indexed: bool


class Passage(BaseModel):
    chunk_id: str
    seq: int
    section: str
    text: str


class DocumentPage(BaseModel):
    doc_id: str
    name: str
    page_number: int
    total_pages: int | None
    passages: list[Passage]


class OutlineSection(BaseModel):
    section: str
    page_number: int
    passages: int


class DocumentOutline(BaseModel):
    doc_id: str
    name: str
    sections: list[OutlineSection]


# ── Admin ────────────────────────────────────────────────────────────────────

class IngestJob(BaseModel):
    id: str
    doc_id: str
    filename: str
    status: Literal["queued", "running", "succeeded", "failed"]
    stage: str | None
    progress: float
    result: dict | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class DocumentMetadataUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    circular_id: str | None = Field(None, max_length=120)
    category: Literal["RBI", "SEBI", "AA", "GENERAL"] | None = None
    subcategory: str | None = Field(None, max_length=120)
    date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    issuer: str | None = Field(None, max_length=200)
    url: str | None = Field(None, max_length=500)


class DeleteResult(BaseModel):
    deleted: bool
    doc_id: str
    file_deleted: bool = False


# ── Meta / health ────────────────────────────────────────────────────────────

class HealthStatus(BaseModel):
    status: Literal["ok"]
    version: str


class ReadinessCheck(BaseModel):
    ok: bool
    detail: str | None = None
    latency_ms: int | None = None


class ReadinessStatus(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, ReadinessCheck]
