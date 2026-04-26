"""
Groq LLM client wrapper with retry logic and error handling.
Uses llama-3.3-70b-versatile — best free model for long-context RAG.
"""

import time
from groq import Groq, RateLimitError
from loguru import logger
from config import settings
from llm.prompt_templates import (
    SYSTEM_PROMPT,
    QUERY_PROMPT_TEMPLATE,
    FOLLOWUP_PROMPT_TEMPLATE,
    format_context,
    format_history,
)


_groq_client: Groq | None = None


def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


def generate_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] | None = None,
    max_tokens: int = 1024,
) -> dict:
    """
    Generates a grounded answer using retrieved chunks as context.

    Args:
        question: User's question
        chunks: Retrieved document chunks from Qdrant
        history: Optional conversation history (list of {question, answer})
        max_tokens: Max tokens for the response

    Returns:
        Dict with answer, sources, and token usage
    """
    client = get_groq_client()
    context = format_context(chunks)

    if history:
        user_content = (
            FOLLOWUP_PROMPT_TEMPLATE
            .replace("{context}", context)
            .replace("{history}", format_history(history))
            .replace("{question}", question)
        )
    else:
        user_content = (
            QUERY_PROMPT_TEMPLATE
            .replace("{context}", context)
            .replace("{question}", question)
        )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )

            answer = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            sources = [
                {
                    "doc_name": c["doc_name"],
                    "circular_id": c["circular_id"],
                    "category": c["category"],
                    "page_number": c["page_number"],
                    "date": c.get("date", ""),
                    "source_url": c.get("source_url", ""),
                    "snippet": c["chunk_text"][:300] + "..." if len(c["chunk_text"]) > 300 else c["chunk_text"],
                    "relevance_score": c.get("relevance_score", 0),
                    "citation": c.get("citation", ""),
                }
                for c in chunks
            ]

            logger.info(f"Answer generated | tokens: {usage['total_tokens']}")
            return {
                "answer": answer,
                "sources": sources,
                "usage": usage,
                "chunks_used": len(chunks),
            }

        except RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt * 5
                logger.warning(
                    f"Rate limit hit. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait_time)
            else:
                raise

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise

    raise RuntimeError("generate_answer exhausted retries without returning")
