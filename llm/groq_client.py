"""
Groq LLM client — regulatory (grounded) and general finance modes.
Supports full responses and streaming with usage + retries.
"""

import time
from collections.abc import Iterator
from groq import Groq, RateLimitError
from loguru import logger
from config import settings
from llm.prompt_templates import (
    REGULATORY_SYSTEM_PROMPT,
    REGULATORY_QUERY_TEMPLATE,
    REGULATORY_FOLLOWUP_TEMPLATE,
    GENERAL_SYSTEM_PROMPT,
    GENERAL_QUERY_TEMPLATE,
    GENERAL_FOLLOWUP_TEMPLATE,
    NOT_FOUND_ANSWER,
    format_context,
    format_history,
)


_groq_client: Groq | None = None


def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


def _build_messages(
    question: str,
    chunks: list[dict],
    history: list[dict] | None,
    is_grounded: bool,
) -> tuple[str, str]:
    if is_grounded:
        system = REGULATORY_SYSTEM_PROMPT
        context = format_context(chunks)
        if history:
            user = (
                REGULATORY_FOLLOWUP_TEMPLATE
                .replace("{context}", context)
                .replace("{history}", format_history(history))
                .replace("{question}", question)
            )
        else:
            user = (
                REGULATORY_QUERY_TEMPLATE
                .replace("{context}", context)
                .replace("{question}", question)
            )
    else:
        system = GENERAL_SYSTEM_PROMPT
        if history:
            user = (
                GENERAL_FOLLOWUP_TEMPLATE
                .replace("{history}", format_history(history))
                .replace("{question}", question)
            )
        else:
            user = GENERAL_QUERY_TEMPLATE.replace("{question}", question)
    return system, user


def _build_sources(chunks: list[dict]) -> list[dict]:
    return [
        {
            "doc_name": c["doc_name"],
            "circular_id": c["circular_id"],
            "category": c["category"],
            "page_number": c["page_number"],
            "date": c.get("date", ""),
            "source_url": c.get("source_url", ""),
            "snippet": (
                c["chunk_text"][:300] + "..."
                if len(c["chunk_text"]) > 300
                else c["chunk_text"]
            ),
            "relevance_score": c.get("relevance_score", 0),
            "citation": c.get("citation", ""),
        }
        for c in chunks
    ]


def not_found_response() -> dict:
    return {
        "answer": NOT_FOUND_ANSWER,
        "sources": [],
        "usage": {},
        "chunks_used": 0,
        "mode": "not_found",
    }


def generate_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
    is_grounded: bool = True,
    max_tokens: int = 2048,
) -> dict:
    """Non-streaming full answer."""
    if not is_grounded and not chunks:
        # Caller decides general vs not_found; this path is for general
        pass

    client = get_groq_client()
    system, user_content = _build_messages(question, chunks, history, is_grounded)

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            mode = "regulatory" if is_grounded else "general"
            logger.info(f"Answer generated | mode={mode} | tokens={usage['total_tokens']}")
            return {
                "answer": response.choices[0].message.content or "",
                "sources": _build_sources(chunks) if is_grounded else [],
                "usage": usage,
                "chunks_used": len(chunks) if is_grounded else 0,
                "mode": mode,
            }
        except RateLimitError:
            if attempt < 2:
                wait = 2 ** attempt * 5
                logger.warning(f"Rate limit. Waiting {wait}s")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise
    raise RuntimeError("generate_answer exhausted retries")


def generate_answer_stream(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
    is_grounded: bool = True,
    max_tokens: int = 2048,
) -> Iterator[dict]:
    """
    Streaming generator yielding event dicts:
      {"type": "token", "content": "..."}
      {"type": "usage", "usage": {...}}
      {"type": "error", "content": "..."}
    """
    client = get_groq_client()
    system, user_content = _build_messages(question, chunks, history, is_grounded)

    for attempt in range(3):
        try:
            stream = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield {"type": "token", "content": delta}
            return
        except RateLimitError:
            if attempt < 2:
                wait = 2 ** attempt * 5
                logger.warning(f"Stream rate limit. Waiting {wait}s")
                time.sleep(wait)
            else:
                yield {
                    "type": "error",
                    "content": "Rate limit reached. Please wait a moment and try again.",
                }
                return
        except Exception as e:
            logger.error(f"Groq streaming error: {e}")
            yield {"type": "error", "content": str(e)}
            return
