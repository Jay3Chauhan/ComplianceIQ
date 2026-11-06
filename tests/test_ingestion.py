"""Unit tests for chunking and the document registry."""

import json

from ingestion import registry
from ingestion.chunker import chunk_id_for, create_chunks


def _page(blocks: list[dict], page_number: int = 1) -> dict:
    return {
        "page_number": page_number,
        "total_pages": 3,
        "text": "\n".join(b["text"] for b in blocks),
        "blocks": blocks,
        "doc_id": "test-doc",
        "doc_name": "Test Doc",
        "circular_id": "TEST/001",
        "category": "RBI",
        "subcategory": "Test",
        "date": "2024-01-01",
        "issuer": "Test Issuer",
        "filename": "test.pdf",
        "source_url": "https://example.com",
    }


def _para(text: str, section: str = "Chapter I › 1. Scope") -> dict:
    return {"text": text, "section": section}


def test_chunks_carry_metadata_section_and_context() -> None:
    long = "This is a compliance sentence about customer due diligence. " * 40
    chunks = create_chunks([_page([_para(long)], page_number=7)])
    assert len(chunks) > 1
    for c in chunks:
        assert c["page_number"] == 7
        assert c["section"] == "Chapter I › 1. Scope"
        assert c["embed_text"].startswith("Document: Test Doc\nSection: Chapter I › 1. Scope")
        assert "Page 7" in c["citation"]
        for key in ("doc_id", "doc_name", "circular_id", "category", "date", "source_url", "seq"):
            assert key in c


def test_chunk_ids_are_deterministic_and_sequential() -> None:
    pages = [_page([_para("Regulated entities shall maintain records of transactions. " * 30)], p) for p in (1, 2)]
    first = create_chunks(pages)
    second = create_chunks(pages)
    assert [c["chunk_id"] for c in first] == [c["chunk_id"] for c in second]
    assert [c["seq"] for c in first] == list(range(len(first)))
    assert first[0]["chunk_id"] == chunk_id_for("test.pdf", 0)


def test_section_switches_inside_page() -> None:
    blocks = [
        _para("Old section text that is long enough to be kept as a passage. " * 6, "A › Old"),
        {"text": "2. New Heading", "section": "A › 2. New Heading", "is_heading": True},
        _para("New section text that is also long enough to be kept as a passage. " * 14, "A › 2. New Heading"),
    ]
    chunks = create_chunks([_page(blocks)])
    assert chunks[0]["section"] == "A › Old"
    assert chunks[-1]["section"] == "A › 2. New Heading"


def test_tiny_and_numeric_text_is_skipped() -> None:
    assert create_chunks([_page([_para("short")])]) == []
    assert create_chunks([_page([_para(" ".join(str(i) for i in range(200)))])]) == []


def test_registry_roundtrip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps([{"filename": "A.pdf", "name": "A", "category": "RBI"}]))
    monkeypatch.setattr(registry, "REGISTRY_PATH", path)

    assert registry.get_entry("a")["filename"] == "A.pdf"
    registry.upsert_entry({"filename": "B b.pdf", "name": "B", "category": "SEBI"})
    assert registry.get_entry("b-b")["name"] == "B"
    assert registry.remove_entry("A.pdf")
    assert [e["filename"] for e in registry.load_registry()] == ["B b.pdf"]


def test_safe_filename() -> None:
    assert registry.safe_filename("../../etc/passwd") == "passwd.pdf"
    assert registry.safe_filename("RBI circular (2024).PDF") == "RBI_circular_2024.pdf"
