"""Tests for retrieval helpers. Most are skipped without a live Qdrant."""

import os
import pytest


QDRANT_AVAILABLE = bool(os.getenv("QDRANT_URL")) and bool(os.getenv("QDRANT_API_KEY"))


@pytest.mark.skipif(not QDRANT_AVAILABLE, reason="Qdrant credentials not configured")
def test_retriever_returns_list() -> None:
    from retrieval.retriever import retrieve_chunks

    chunks = retrieve_chunks("What are KYC norms?", top_k=3)
    assert isinstance(chunks, list)
    for c in chunks:
        assert "chunk_text" in c
        assert "doc_name" in c
        assert "relevance_score" in c


@pytest.mark.skipif(not QDRANT_AVAILABLE, reason="Qdrant credentials not configured")
def test_get_all_documents_returns_list() -> None:
    from retrieval.retriever import get_all_documents

    docs = get_all_documents()
    assert isinstance(docs, list)
