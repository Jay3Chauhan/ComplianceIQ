"""
Retrieves relevant document chunks from Qdrant using vector similarity search.
Supports category filtering, date filtering, and configurable top-k.
"""

from qdrant_client.models import Filter, FieldCondition, MatchValue
from loguru import logger
from ingestion.embedder import get_qdrant_client, embed_query
from config import settings


def retrieve_chunks(
    query: str,
    top_k: int | None = None,
    category_filter: str | None = None,
    score_threshold: float = 0.35,
) -> list[dict]:
    """
    Retrieves top-k most relevant chunks for a query.

    Args:
        query: User's natural language question
        top_k: Number of chunks to retrieve (default from settings)
        category_filter: Optional filter by document category ("RBI", "SEBI", "AA", or None/ALL)
        score_threshold: Minimum cosine similarity score (0-1)

    Returns:
        List of chunk dicts with payload + score, sorted by relevance
    """
    if top_k is None:
        top_k = settings.max_retrieval_chunks

    client = get_qdrant_client()
    query_vector = embed_query(query)

    search_filter = None
    if category_filter and category_filter.upper() != "ALL":
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category_filter.upper()),
                )
            ]
        )

    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
        query_filter=search_filter,
        score_threshold=score_threshold,
        with_payload=True,
    )

    chunks: list[dict] = []
    for result in response.points:
        chunk = {**result.payload, "relevance_score": round(result.score, 4)}
        chunks.append(chunk)

    logger.debug(f"Retrieved {len(chunks)} chunks for query: '{query[:60]}...'")
    return chunks


def get_all_documents() -> list[dict]:
    """Returns metadata for all unique documents in the collection."""
    client = get_qdrant_client()

    seen_docs: set[str] = set()
    documents: list[dict] = []
    offset = None

    while True:
        results, next_offset = client.scroll(
            collection_name=settings.qdrant_collection,
            limit=100,
            offset=offset,
            with_payload=["doc_name", "circular_id", "category", "date", "issuer", "source_url"],
        )

        for point in results:
            doc_name = point.payload.get("doc_name", "")
            if doc_name and doc_name not in seen_docs:
                seen_docs.add(doc_name)
                documents.append({
                    "doc_name": doc_name,
                    "circular_id": point.payload.get("circular_id", ""),
                    "category": point.payload.get("category", ""),
                    "date": point.payload.get("date", ""),
                    "issuer": point.payload.get("issuer", ""),
                    "source_url": point.payload.get("source_url", ""),
                })

        if next_offset is None:
            break
        offset = next_offset

    return sorted(documents, key=lambda x: (x["category"], x["doc_name"]))
