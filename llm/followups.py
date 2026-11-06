"""
Suggested next questions and short conversation titles.

One small JSON call to the fast model after an answer is final. Failures are
silent: the answer is already complete, so these are best-effort extras.
"""

import re

from loguru import logger

from config import settings
from llm.groq_client import complete_json

MAX_FOLLOWUPS = 3
MAX_FOLLOWUP_CHARS = 120
MAX_TITLE_WORDS = 8

FOLLOWUP_SYSTEM_PROMPT = """You support ComplianceIQ, a Q&A assistant for Indian financial regulation (RBI, SEBI, Account Aggregator).
Given a user's question and the assistant's answer, respond with JSON only:
{"title": "...", "followups": ["...", "...", "..."]}

title: 3 to 7 words naming the regulatory topic, Title Case, no quotes, no trailing punctuation.
followups: up to 3 questions the user is likely to ask next.
- Each under 15 words, self-contained (no "it" or "this"), ending with "?".
- Stay on the same regulation or closely related obligations.
- Do not repeat or rephrase the original question.
- Do not mention circular numbers, dates or figures that are not in the answer."""

FOLLOWUP_USER_TEMPLATE = """Question: {question}

Answer:
{answer}"""


def _clean_followups(items: object, question: str) -> list[str]:
    if not isinstance(items, list):
        return []
    seen = {question.strip().lower()}
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split()).strip(" -•\"'")
        if not text or len(text) > MAX_FOLLOWUP_CHARS or text.lower() in seen:
            continue
        if not text.endswith("?"):
            text += "?"
        seen.add(text.lower())
        out.append(text)
        if len(out) == MAX_FOLLOWUPS:
            break
    return out


def _clean_title(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    title = re.sub(r"[\"'`*#]", "", " ".join(value.split())).strip(" .:-")
    if not title:
        return None
    words = title.split()
    return " ".join(words[:MAX_TITLE_WORDS])


def suggest(question: str, answer: str, want_followups: bool = True, want_title: bool = False) -> dict:
    """Returns {"followups": [...], "title": str | None}; empty values when disabled or on failure."""
    result: dict = {"followups": [], "title": None}
    want_followups = want_followups and settings.enable_followups
    want_title = want_title and settings.enable_llm_titles
    if not (want_followups or want_title) or not answer.strip():
        return result
    try:
        data = complete_json(
            [
                {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
                {"role": "user", "content": FOLLOWUP_USER_TEMPLATE.format(
                    question=question.strip()[:500], answer=answer.strip()[:2500],
                )},
            ],
            model=settings.groq_fast_model,
            max_tokens=250,
            allow_fallback=False,
        )
    except Exception as e:
        logger.warning(f"Follow-up suggestions failed: {e}")
        return result
    if want_followups:
        result["followups"] = _clean_followups(data.get("followups"), question)
    if want_title:
        result["title"] = _clean_title(data.get("title"))
    return result
