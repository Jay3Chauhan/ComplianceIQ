"""
End-to-end RAG pipeline: rewrite → retrieve → gate → generate → verify → repair.

`answer()` returns a complete RAGResponse; `stream()` yields events for SSE:
  status        {"stage": understanding|searching|thinking|writing|verifying|revising|done}
  retrieval     {"mode", "grounded", "gate_score", "standalone_question", "sources"}
  token         {"content"}
  verification  {...VerificationReport}
  revision      {"answer"}          (replaces the streamed answer)
  usage         {...}
  done          {"latency_ms", "confidence", "mode", "model"}
  error         {"code", "message"}
"""

import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Literal

from loguru import logger

from config import settings
from llm import groq_client
from llm.prompt_templates import (
    GENERAL_SYSTEM_PROMPT,
    GENERAL_USER_TEMPLATE,
    NOT_FOUND_ANSWER,
    REGULATORY_SYSTEM_PROMPT,
    REGULATORY_USER_TEMPLATE,
    REPAIR_USER_TEMPLATE,
    format_context,
    history_block,
)
from llm.query_rewriter import needs_rewrite, rewrite_query
from llm.verifier import CITATION_RE, VerificationReport, verify_answer
from retrieval.retriever import RetrievalResult, retrieve

AnswerMode = Literal["auto", "regulatory", "general"]
REFUSAL_MARKER = "do not contain enough information"


def is_refusal(text: str) -> bool:
    """A refusal only if the model cited nothing; cited partial answers are kept."""
    return REFUSAL_MARKER in text.lower() and not CITATION_RE.search(text)


@dataclass
class RAGRequest:
    question: str
    category: str = "ALL"
    top_k: int | None = None
    answer_mode: AnswerMode = "auto"
    history: list[dict] | None = None
    verify: bool | None = None


@dataclass
class RAGResponse:
    answer: str
    mode: str
    sources: list[dict]
    standalone_question: str
    grounded: bool
    gate_score: float
    verification: dict | None = None
    revised: bool = False
    confidence: str | None = None
    model: str | None = None
    usage: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Building blocks ──────────────────────────────────────────────────────────

def build_sources(chunks: list[dict]) -> list[dict]:
    sources = []
    for i, c in enumerate(chunks, 1):
        text = c["chunk_text"]
        sources.append({
            "id": i,
            "chunk_id": c.get("chunk_id", ""),
            "doc_id": c.get("doc_id", ""),
            "doc_name": c["doc_name"],
            "circular_id": c.get("circular_id", ""),
            "category": c.get("category", ""),
            "section": c.get("section", ""),
            "page_number": c.get("page_number", 0),
            "date": c.get("date", ""),
            "source_url": c.get("source_url", ""),
            "filename": c.get("filename", ""),
            "snippet": text[:320] + ("…" if len(text) > 320 else ""),
            "text": text,
            "relevance_score": round(float(c.get("relevance_score", 0.0)), 4),
            "citation": c.get("citation", ""),
        })
    return sources


def _resolve_mode(answer_mode: str, grounded: bool) -> str:
    if answer_mode == "general":
        return "general"
    if grounded:
        return "regulatory"
    return "not_found" if answer_mode == "regulatory" else "general"


def _messages(mode: str, question: str, chunks: list[dict], history: list[dict] | None) -> list[dict]:
    if mode == "regulatory":
        user = REGULATORY_USER_TEMPLATE.format(
            context=format_context(chunks, max_chars=settings.max_context_chars),
            history_block=history_block(history),
            question=question,
        )
        return [{"role": "system", "content": REGULATORY_SYSTEM_PROMPT}, {"role": "user", "content": user}]
    user = GENERAL_USER_TEMPLATE.format(history_block=history_block(history), question=question)
    return [{"role": "system", "content": GENERAL_SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _confidence(mode: str, retrieval: RetrievalResult | None, report: VerificationReport | None) -> str | None:
    if mode == "not_found":
        return None
    if mode == "general":
        return "low"
    if report is None or report.status == "not_applicable":
        return "medium"
    if report.status == "verified" and retrieval and retrieval.gate_score >= 0.5:
        return "high"
    if report.status in ("verified", "partially_verified"):
        return "medium"
    return "low"


def _should_verify(req: RAGRequest) -> bool:
    return settings.enable_verification if req.verify is None else req.verify


def _repair(question: str, answer: str, chunks: list[dict], report: VerificationReport) -> tuple[str, VerificationReport] | None:
    """One repair pass; keeps the repaired answer only if it verifies better."""
    try:
        result = groq_client.complete([
            {"role": "system", "content": REGULATORY_SYSTEM_PROMPT},
            {"role": "user", "content": REPAIR_USER_TEMPLATE.format(
                context=format_context(chunks, max_chars=settings.max_context_chars),
                question=question,
                answer=answer,
                problems="\n".join(report.problems()[:12]),
            )},
        ])
    except Exception as e:
        logger.warning(f"Answer repair failed: {e}")
        return None
    repaired = result.content.strip()
    if not repaired:
        return None
    new_report = verify_answer(repaired, chunks)
    if new_report.score >= report.score:
        return repaired, new_report
    return None


def _retrieve(req: RAGRequest, search_question: str) -> RetrievalResult | None:
    if req.answer_mode == "general":
        return None
    return retrieve(search_question, top_k=req.top_k, category=req.category)


# ── Public API ───────────────────────────────────────────────────────────────

def answer(req: RAGRequest) -> RAGResponse:
    t0 = time.perf_counter()
    standalone = rewrite_query(req.question, req.history) if req.answer_mode != "general" else req.question
    retrieval = _retrieve(req, standalone)
    grounded = bool(retrieval and retrieval.is_grounded)
    mode = _resolve_mode(req.answer_mode, grounded)
    chunks = retrieval.chunks if (retrieval and mode == "regulatory") else []

    base = dict(
        standalone_question=standalone,
        grounded=grounded,
        gate_score=retrieval.gate_score if retrieval else 0.0,
        timings=dict(retrieval.timings) if retrieval else {},
    )

    if mode == "not_found":
        return RAGResponse(answer=NOT_FOUND_ANSWER, mode=mode, sources=[], confidence=None,
                           latency_ms=round((time.perf_counter() - t0) * 1000), **base)

    t_gen = time.perf_counter()
    completion = groq_client.complete(_messages(mode, req.question, chunks, req.history))
    base["timings"]["generation_ms"] = round((time.perf_counter() - t_gen) * 1000)
    text = completion.content.strip()

    report: VerificationReport | None = None
    revised = False
    if mode == "regulatory":
        if is_refusal(text):
            mode, chunks, text = "not_found", [], NOT_FOUND_ANSWER
        elif _should_verify(req):
            t_ver = time.perf_counter()
            report = verify_answer(text, chunks)
            if report.needs_repair and settings.enable_answer_repair:
                fixed = _repair(req.question, text, chunks, report)
                if fixed:
                    text, report = fixed
                    revised = True
            base["timings"]["verification_ms"] = round((time.perf_counter() - t_ver) * 1000)

    return RAGResponse(
        answer=text,
        mode=mode,
        sources=build_sources(chunks),
        verification=report.to_dict() if report else None,
        revised=revised,
        confidence=_confidence(mode, retrieval, report),
        model=completion.model,
        usage=completion.usage,
        latency_ms=round((time.perf_counter() - t0) * 1000),
        **base,
    )


def stream(req: RAGRequest) -> Iterator[dict]:
    t0 = time.perf_counter()
    try:
        standalone = req.question
        if req.answer_mode != "general" and needs_rewrite(req.question, req.history):
            yield {"type": "status", "stage": "understanding", "message": "Understanding your follow-up…"}
            standalone = rewrite_query(req.question, req.history)

        retrieval: RetrievalResult | None = None
        if req.answer_mode != "general":
            yield {"type": "status", "stage": "searching", "message": "Searching regulatory documents…"}
            retrieval = _retrieve(req, standalone)

        grounded = bool(retrieval and retrieval.is_grounded)
        mode = _resolve_mode(req.answer_mode, grounded)
        chunks = retrieval.chunks if (retrieval and mode == "regulatory") else []
        yield {
            "type": "retrieval",
            "mode": mode,
            "grounded": grounded,
            "gate_score": retrieval.gate_score if retrieval else 0.0,
            "standalone_question": standalone,
            "sources": build_sources(chunks),
            "timings": retrieval.timings if retrieval else {},
        }

        if mode == "not_found":
            yield {"type": "token", "content": NOT_FOUND_ANSWER}
            yield {"type": "done", "mode": mode, "confidence": None, "model": None,
                   "latency_ms": round((time.perf_counter() - t0) * 1000)}
            return

        yield {"type": "status", "stage": "thinking", "message": "Reading the sources…" if chunks else "Thinking…"}
        parts: list[str] = []
        model: str | None = None
        writing = False
        for event in groq_client.stream(_messages(mode, req.question, chunks, req.history)):
            if event["type"] == "model":
                model = event["model"]
            elif event["type"] == "token":
                if not writing:
                    writing = True
                    yield {"type": "status", "stage": "writing", "message": "Writing answer…"}
                parts.append(event["content"])
                yield event
            elif event["type"] == "error":
                yield event
                return

        raw = "".join(parts).strip()
        text = groq_client.clean_text(raw)
        if text != raw:
            yield {"type": "revision", "answer": text, "mode": mode}
        report: VerificationReport | None = None
        if mode == "regulatory" and is_refusal(text):
            mode = "not_found"
            yield {"type": "revision", "answer": NOT_FOUND_ANSWER, "mode": mode, "sources": []}
        elif mode == "regulatory" and _should_verify(req):
            yield {"type": "status", "stage": "verifying", "message": "Checking every claim against the sources…"}
            report = verify_answer(text, chunks)
            if report.needs_repair and settings.enable_answer_repair:
                yield {"type": "verification", **report.to_dict(), "final": False}
                yield {"type": "status", "stage": "revising", "message": "Fixing unsupported statements…"}
                fixed = _repair(req.question, text, chunks, report)
                if fixed:
                    text, report = fixed
                    yield {"type": "revision", "answer": text, "mode": mode}
            yield {"type": "verification", **report.to_dict(), "final": True}

        yield {
            "type": "done",
            "mode": mode,
            "answer": text if mode != "not_found" else NOT_FOUND_ANSWER,
            "confidence": _confidence(mode, retrieval, report),
            "model": model,
            "latency_ms": round((time.perf_counter() - t0) * 1000),
        }
    except groq_client.LLMUnavailableError:
        yield {"type": "error", "code": "rate_limited",
               "message": "The language model is rate limited. Please wait a minute and try again."}
    except Exception as e:
        logger.exception(f"RAG stream failed: {e}")
        yield {"type": "error", "code": "internal_error", "message": "Something went wrong while answering."}
