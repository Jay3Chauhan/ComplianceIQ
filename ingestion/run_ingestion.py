"""
CLI script to ingest PDFs into Qdrant.
Usage: python -m ingestion.run_ingestion
       python -m ingestion.run_ingestion --file RBI_KYC_Master_Direction_2016.pdf
       python -m ingestion.run_ingestion --category RBI
"""

import json
import argparse
from pathlib import Path
from loguru import logger
from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store


REGISTRY_PATH = "data/document_registry.json"
DOCS_DIR = "data/documents"


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def ingest_document(doc_meta: dict) -> dict:
    """Ingests a single document. Returns stats."""
    pdf_path = Path(DOCS_DIR) / doc_meta["filename"]

    if not pdf_path.exists():
        logger.warning(f"PDF not found, skipping: {pdf_path}")
        return {"status": "skipped", "reason": "file not found"}

    logger.info(f"Ingesting: {doc_meta['name']}")

    pages = parse_pdf(str(pdf_path), doc_meta)
    chunks = create_chunks(pages)
    stored = embed_and_store(chunks)

    return {
        "status": "success",
        "doc_name": doc_meta["name"],
        "pages": len(pages),
        "chunks": len(chunks),
        "vectors_stored": stored,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into ComplianceIQ")
    parser.add_argument("--category", help="Filter by category: RBI, SEBI, AA")
    parser.add_argument("--file", help="Ingest a specific filename from the registry")
    args = parser.parse_args()

    registry = load_registry()

    if args.file:
        registry = [d for d in registry if d["filename"] == args.file]
    elif args.category:
        registry = [d for d in registry if d["category"] == args.category.upper()]

    logger.info(f"Starting ingestion of {len(registry)} documents")
    results: list[dict] = []

    for doc in registry:
        result = ingest_document(doc)
        results.append(result)

    success = [r for r in results if r.get("status") == "success"]
    logger.success(
        f"Ingestion complete: {len(success)}/{len(results)} documents | "
        f"{sum(r.get('chunks', 0) for r in success)} total chunks stored"
    )


if __name__ == "__main__":
    main()
