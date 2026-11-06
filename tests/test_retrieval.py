"""Retrieval helpers (unit) + live retrieval (set RUN_INTEGRATION=1 with Qdrant credentials)."""

import os
import time

import pytest

from api.security import SlidingWindowLimiter
from retrieval.cache import TTLCache, clear_all_caches
from retrieval.glossary import expand_query

INTEGRATION = os.getenv("RUN_INTEGRATION") == "1"


def test_expand_query_adds_known_acronyms_once() -> None:
    q = expand_query("What is the KFS requirement for a DLA?")
    assert "Key Fact Statement (KFS)" in q
    assert "Digital Lending App (DLA)" in q
    assert expand_query("What is a Key Fact Statement (KFS)?").count("Key Fact Statement") == 1
    assert expand_query("plain question without acronyms") == "plain question without acronyms"


def test_ttl_cache_expires_and_clears() -> None:
    cache = TTLCache(ttl_seconds=1, max_items=2)
    cache.set("a", 1)
    assert cache.get("a") == 1
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None  # evicted (max_items)
    clear_all_caches()
    assert cache.get("b") is None
    cache.set("d", 4)
    time.sleep(1.1)
    assert cache.get("d") is None


def test_sliding_window_limiter() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_s=60)
    assert limiter.check("k")[0]
    assert limiter.check("k")[0]
    allowed, retry_after = limiter.check("k")
    assert not allowed and retry_after > 0
    assert limiter.check("other")[0]


@pytest.mark.skipif(not INTEGRATION, reason="set RUN_INTEGRATION=1 to hit live Qdrant")
def test_live_hybrid_retrieval_grounded() -> None:
    from retrieval.retriever import retrieve

    result = retrieve("What is the Key Fact Statement for digital loans?", top_k=4, rerank=True, use_cache=False)
    assert result.is_grounded
    assert result.chunks and "Digital_Lending" in result.chunks[0]["filename"]
    assert all("section" in c and "relevance_score" in c for c in result.chunks)


@pytest.mark.skipif(not INTEGRATION, reason="set RUN_INTEGRATION=1 to hit live Qdrant")
def test_live_gate_rejects_out_of_scope() -> None:
    from retrieval.retriever import retrieve

    result = retrieve("How do I bake a chocolate cake at home?", rerank=True, use_cache=False)
    assert not result.is_grounded
    assert result.chunks == []
