"""
Groq chat client with retries and automatic fallback to a smaller model when
the primary model is rate limited (common on the free tier).
"""

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
from loguru import logger

from config import settings

_client: Groq | None = None

MAX_INLINE_WAIT_S = 8.0


class LLMUnavailableError(RuntimeError):
    """All configured models are rate limited or unreachable."""


def get_groq_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key, max_retries=0, timeout=60)
    return _client


@dataclass
class Completion:
    content: str
    model: str
    usage: dict = field(default_factory=dict)


def _retry_after(err: RateLimitError) -> float:
    try:
        return float(err.response.headers.get("retry-after", "0"))
    except (AttributeError, ValueError):
        return 0.0


def _models(primary: str | None) -> list[str]:
    return list(dict.fromkeys([primary or settings.groq_model, *settings.fallback_model_list]))


# gpt-oss emits typographic spacing/hyphens and 【n】-style citations
_CHAR_MAP = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u00ad": "",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u2007": " ", "\u200b": "",
    "【": "[", "】": "]",
})
_DAGGER_CITATION_RE = re.compile(r"\[(\d{1,2})†[^\]]*\]")


def clean_text(text: str) -> str:
    """Normalizes model output so citations and figures match the source passages."""
    return _DAGGER_CITATION_RE.sub(r"[\1]", text.translate(_CHAR_MAP))


def _is_reasoning(model: str) -> bool:
    return model.startswith("openai/gpt-oss")


def _model_kwargs(model: str, max_tokens: int | None = None) -> dict:
    """Per-family options: keep reasoning short and out of the visible answer.

    Groq reserves max_completion_tokens against the per-minute token limit, so
    non-reasoning models get only the visible budget.
    """
    budget = max_tokens or settings.llm_max_tokens
    if _is_reasoning(model):
        return {
            "max_completion_tokens": budget + settings.llm_reasoning_allowance,
            "reasoning_effort": settings.llm_reasoning_effort,
            "include_reasoning": False,
        }
    if model.startswith("qwen/qwen3"):
        return {"max_completion_tokens": budget, "reasoning_effort": "none"}
    return {"max_completion_tokens": budget}


def _usage(resp) -> dict:
    u = getattr(resp, "usage", None)
    if not u:
        return {}
    return {
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "total_tokens": u.total_tokens,
    }


def complete(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    allow_fallback: bool = True,
) -> Completion:
    """Non-streaming completion. Falls back to the secondary model on rate limits."""
    candidates = _models(model) if allow_fallback else [model or settings.groq_model]
    last_error: Exception | None = None

    for name in candidates:
        for attempt in range(2):
            try:
                kwargs: dict = {
                    "model": name,
                    "messages": messages,
                    "temperature": settings.llm_temperature if temperature is None else temperature,
                    **_model_kwargs(name, max_tokens),
                }
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                resp = get_groq_client().chat.completions.create(**kwargs)
                return Completion(clean_text(resp.choices[0].message.content or ""), name, _usage(resp))
            except RateLimitError as e:
                last_error = e
                wait = _retry_after(e)
                if attempt == 0 and 0 < wait <= MAX_INLINE_WAIT_S:
                    logger.warning(f"{name} rate limited; retrying in {wait:.0f}s")
                    time.sleep(wait)
                    continue
                logger.warning(f"{name} rate limited; trying next model")
                break
            except APIConnectionError as e:
                last_error = e
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                break
            except APIStatusError as e:
                last_error = e
                if e.status_code >= 500 and attempt == 0:
                    time.sleep(1.5)
                    continue
                if e.status_code == 404:  # model retired or not enabled for this key
                    logger.error(f"Model {name} unavailable: {e}")
                    break
                raise
    raise LLMUnavailableError(str(last_error) if last_error else "LLM unavailable")


def complete_json(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 800,
    allow_fallback: bool = True,
) -> dict:
    result = complete(
        messages, model=model, max_tokens=max_tokens, temperature=0.0, json_mode=True, allow_fallback=allow_fallback
    )
    try:
        return json.loads(result.content)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON")
        return {}


def stream(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> Iterator[dict]:
    """
    Streams a completion as events:
      {"type": "token", "content": str}
      {"type": "model", "model": str}       (once, before the first token)
      {"type": "error", "code": str, "message": str}
    Falls back to the secondary model only if no tokens were emitted yet.
    """
    last_error = ""
    for name in _models(model):
        emitted = False
        try:
            s = get_groq_client().chat.completions.create(
                model=name,
                messages=messages,
                temperature=settings.llm_temperature if temperature is None else temperature,
                stream=True,
                **_model_kwargs(name, max_tokens),
            )
            for chunk in s:
                if not chunk.choices:
                    continue
                delta = (chunk.choices[0].delta.content or "").translate(_CHAR_MAP)
                if delta:
                    if not emitted:
                        yield {"type": "model", "model": name}
                        emitted = True
                    yield {"type": "token", "content": delta}
            return
        except RateLimitError as e:
            last_error = str(e)
            logger.warning(f"{name} rate limited during stream")
            if emitted:
                break
        except Exception as e:
            logger.error(f"Groq streaming error ({name}): {e}")
            if emitted or not (isinstance(e, APIStatusError) and e.status_code == 404):
                yield {"type": "error", "code": "llm_error", "message": "The language model failed to respond."}
                return
            last_error = str(e)
    yield {
        "type": "error",
        "code": "rate_limited",
        "message": "The language model is rate limited. Please wait a minute and try again.",
    }
    logger.error(f"All models rate limited: {last_error[:200]}")
