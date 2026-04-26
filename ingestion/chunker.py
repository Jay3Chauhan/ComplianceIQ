"""
Text chunking with metadata preservation.
Splits pages into overlapping chunks for optimal RAG retrieval.
"""

import uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger
from config import settings


def create_chunks(pages: list[dict]) -> list[dict]:
    """
    Splits page-level text into smaller chunks for embedding.
    Each chunk inherits full metadata from its parent page.

    Returns list of chunk dicts ready for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "। ", ". ", " ", ""],
        length_function=len,
    )

    chunks: list[dict] = []
    for page in pages:
        if not page["text"].strip():
            continue

        text_chunks = splitter.split_text(page["text"])

        for idx, chunk_text in enumerate(text_chunks):
            if len(chunk_text.strip()) < 50:
                continue

            chunk = {
                "chunk_id": str(uuid.uuid4()),
                "chunk_text": chunk_text.strip(),
                "chunk_index": idx,
                "total_chunks_on_page": len(text_chunks),
                "page_number": page["page_number"],
                "total_pages": page["total_pages"],
                "doc_name": page["doc_name"],
                "circular_id": page["circular_id"],
                "category": page["category"],
                "subcategory": page["subcategory"],
                "date": page["date"],
                "issuer": page["issuer"],
                "filename": page["filename"],
                "source_url": page["source_url"],
                "citation": f"{page['doc_name']} | {page['circular_id']} | Page {page['page_number']}",
            }
            chunks.append(chunk)

    logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
    return chunks
