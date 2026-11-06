"""
Section-aware chunking with deterministic IDs and contextual embedding text.

Each chunk stores:
  chunk_text  — the clean passage shown to users and given to the LLM
  embed_text  — "Document / Section" header + passage (what gets embedded)
  section     — nearest chapter/heading label for citations
  seq         — order within the document (stable; used for neighbours)
"""

import uuid
from bisect import bisect_right

from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from config import settings
from ingestion.text_cleaning import is_low_value

CHUNK_NAMESPACE = uuid.UUID("6f1c7a52-3b0e-4c9a-9d55-2d4f8f0b7e11")


def chunk_id_for(filename: str, seq: int) -> str:
    return str(uuid.uuid5(CHUNK_NAMESPACE, f"{filename}:{seq}"))


def build_embed_text(doc_name: str, section: str, text: str) -> str:
    header = f"Document: {doc_name}"
    if section:
        header += f"\nSection: {section}"
    return f"{header}\n\n{text}"


def build_citation(chunk: dict) -> str:
    parts = [chunk["doc_name"]]
    if chunk.get("circular_id"):
        parts.append(chunk["circular_id"])
    if chunk.get("section"):
        parts.append(chunk["section"])
    parts.append(f"Page {chunk['page_number']}")
    return " | ".join(parts)


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n", "; ", ". ", "। ", ", ", " ", ""],
        keep_separator="end",
        add_start_index=True,
    )


def create_chunks(pages: list[dict]) -> list[dict]:
    """Splits cleaned pages into chunks that inherit page + document metadata."""
    splitter = _splitter()
    chunks: list[dict] = []
    seq = 0

    for page in pages:
        blocks = page.get("blocks") or [{"text": page["text"], "section": ""}]
        starts: list[int] = []
        sections: list[str] = []
        text = ""
        for block in blocks:
            starts.append(len(text))
            sections.append(block.get("section", ""))
            text += block["text"] + "\n"

        for doc in splitter.create_documents([text]):
            chunk_text = doc.page_content.strip()
            if is_low_value(chunk_text):
                continue
            # Section of the content a quarter of the way in, so a heading near
            # the top of the chunk wins over the tail of the previous section.
            probe = doc.metadata["start_index"] + min(len(chunk_text) // 4, 200)
            section = sections[max(bisect_right(starts, probe) - 1, 0)]

            chunk = {
                "chunk_id": chunk_id_for(page["filename"], seq),
                "seq": seq,
                "chunk_text": chunk_text,
                "section": section,
                "page_number": page["page_number"],
                "total_pages": page["total_pages"],
                "doc_id": page["doc_id"],
                "doc_name": page["doc_name"],
                "circular_id": page["circular_id"],
                "category": page["category"],
                "subcategory": page["subcategory"],
                "date": page["date"],
                "issuer": page["issuer"],
                "filename": page["filename"],
                "source_url": page["source_url"],
            }
            chunk["citation"] = build_citation(chunk)
            chunk["embed_text"] = build_embed_text(page["doc_name"], section, chunk_text)
            chunks.append(chunk)
            seq += 1

    logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
    return chunks
