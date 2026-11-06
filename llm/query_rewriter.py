"""
Turns follow-up questions ("what about for NBFCs?") into standalone search
queries so retrieval does not depend on conversation context.
"""

import re

from loguru import logger

from config import settings
from llm.groq_client import complete
from llm.prompt_templates import QUERY_REWRITE_PROMPT, format_history

_DEPENDENT_RE = re.compile(
    r"\b(it|its|this|that|these|those|they|them|their|there|above|same|such|former|latter|"
    r"what about|how about|and for|also|else|more|further|previous|earlier)\b",
    re.I,
)


def needs_rewrite(question: str, history: list[dict] | None) -> bool:
    if not history:
        return False
    words = question.split()
    return len(words) <= 6 or bool(_DEPENDENT_RE.search(question))


def rewrite_query(question: str, history: list[dict] | None) -> str:
    """Returns a standalone query (the original question if no rewrite is needed)."""
    if not settings.enable_query_rewrite or not needs_rewrite(question, history):
        return question
    prompt = QUERY_REWRITE_PROMPT.format(history=format_history(history, turns=2, answer_chars=300), question=question)
    try:
        result = complete(
            [{"role": "user", "content": prompt}],
            model=settings.groq_fast_model,
            max_tokens=100,
            temperature=0.0,
        )
        rewritten = result.content.strip().strip('"').splitlines()[0].strip()
        if 3 <= len(rewritten) <= 300:
            logger.debug(f"Rewrote follow-up: '{question}' → '{rewritten}'")
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewrite failed, using heuristic: {e}")
    last = (history or [{}])[-1].get("question", "")
    return f"{last} {question}".strip()
