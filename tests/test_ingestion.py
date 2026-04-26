"""Unit tests for the ingestion pipeline."""

from ingestion.chunker import create_chunks


def _sample_page(text: str, page_number: int = 1) -> dict:
    return {
        "page_number": page_number,
        "text": text,
        "total_pages": 1,
        "doc_name": "Test Doc",
        "circular_id": "TEST/001",
        "category": "RBI",
        "subcategory": "Test",
        "date": "2024-01-01",
        "issuer": "Test Issuer",
        "filename": "test.pdf",
        "source_url": "https://example.com",
    }


def test_create_chunks_returns_non_empty() -> None:
    long_text = ("This is a compliance sentence about KYC. " * 100).strip()
    pages = [_sample_page(long_text)]
    chunks = create_chunks(pages)

    assert len(chunks) > 0
    for chunk in chunks:
        assert "chunk_id" in chunk
        assert "chunk_text" in chunk
        assert chunk["doc_name"] == "Test Doc"
        assert chunk["citation"].startswith("Test Doc")


def test_create_chunks_skips_tiny_text() -> None:
    pages = [_sample_page("short")]
    chunks = create_chunks(pages)
    assert chunks == []


def test_create_chunks_preserves_page_metadata() -> None:
    pages = [_sample_page("Detailed regulatory text. " * 50, page_number=7)]
    chunks = create_chunks(pages)
    assert all(c["page_number"] == 7 for c in chunks)
