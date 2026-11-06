"""
CLI script to ingest PDFs into Qdrant.
Usage: python -m ingestion.run_ingestion
       python -m ingestion.run_ingestion --file RBI_KYC_Master_Direction_2016.pdf
       python -m ingestion.run_ingestion --category RBI
       python -m ingestion.run_ingestion --recreate   # drop & rebuild the collection
"""

import argparse

from loguru import logger

from config import settings
from ingestion.embedder import collection_exists, get_qdrant_client
from ingestion.pipeline import ingest_document
from ingestion.registry import load_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into ComplianceIQ")
    parser.add_argument("--category", help="Filter by category: RBI, SEBI, AA")
    parser.add_argument("--file", help="Ingest a specific filename from the registry")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the collection first")
    args = parser.parse_args()

    registry = load_registry()
    if args.file:
        registry = [d for d in registry if d["filename"] == args.file]
    elif args.category:
        registry = [d for d in registry if d["category"] == args.category.upper()]

    if args.recreate and collection_exists():
        logger.warning(f"Dropping collection {settings.qdrant_collection}")
        get_qdrant_client().delete_collection(settings.qdrant_collection)

    logger.info(f"Ingesting {len(registry)} documents into {settings.qdrant_collection}")
    results = [ingest_document(doc) for doc in registry]

    success = [r for r in results if r.get("status") == "success"]
    for r in results:
        logger.info(f"  {r['status']:8} {r.get('doc_name')} — {r.get('chunks', 0)} chunks")
    logger.success(
        f"Ingestion complete: {len(success)}/{len(results)} documents | "
        f"{sum(r.get('chunks', 0) for r in success)} chunks stored"
    )


if __name__ == "__main__":
    main()
