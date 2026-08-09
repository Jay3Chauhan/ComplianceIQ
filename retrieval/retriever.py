"""
Retrieves relevant document chunks from Qdrant with optional cross-encoder rerank
and a confidence gate for regulatory grounding.
"""

from qdrant_client.models import Filter, FieldCondition, MatchValue
from loguru import logger
from ingestion.embedder import get_qdrant_client, embed_query
from config import settings


def retrieve_chunks(
    query: str,
    top_k: int | None = None,
    category_filter: str | None = None,
    score_threshold: float | None = None,
    enable_rerank: bool | None = None,
) -> tuple[list[dict], bool]:
    """
    Retrieve → (optional) rerank → grounding gate.

    Returns:
        (chunks, is_grounded)
    """
    if top_k is None:
        top_k = settings.max_retrieval_chunks
    if score_threshold is None:
        score_threshold = settings.score_threshold
    if enable_rerank is None:
        enable_rerank = settings.enable_rerank

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

    candidate_k = max(top_k * settings.retrieval_candidate_multiplier, top_k)

    def _search(threshold: float, limit: int) -> list[dict]:
        response = client.query_points(
            collection_name=settings.qdrant_collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
            score_threshold=threshold,
            with_payload=True,
        )
        return [
            {**r.payload, "relevance_score": round(r.score, 4)}
            for r in response.points
        ]

    chunks = _search(score_threshold, candidate_k)

    if len(chunks) < 2:
        fallback = _search(settings.score_fallback_threshold, candidate_k)
        if len(fallback) > len(chunks):
            logger.debug(
                f"Threshold fallback: {len(chunks)} → {len(fallback)} chunks"
            )
            chunks = fallback

    if enable_rerank and len(chunks) > 1:
        try:
            from retrieval.reranker import rerank_chunks

            chunks = rerank_chunks(query, chunks, top_k=top_k)
        except Exception as e:
            logger.warning(f"Rerank skipped ({e}); using dense ranking")
            chunks = chunks[:top_k]
    else:
        chunks = chunks[:top_k]

    best = chunks[0]["relevance_score"] if chunks else 0.0
    # After rerank, prefer dense score if present; else use rerank_score scaled
    if chunks and "rerank_score" in chunks[0]:
        # Cross-encoder scores are not cosine; use dense score for gate when available
        best = max(c.get("relevance_score", 0.0) for c in chunks)

    strong_hits = sum(
        1 for c in chunks if c.get("relevance_score", 0) >= score_threshold
    )
    # Require a clearly relevant top hit — avoids forcing "SIP/IPO" style
    # general finance questions into weak regulatory citations.
    is_grounded = bool(
        chunks
        and best >= settings.grounded_min_score
        and strong_hits >= 1
    )

    if not is_grounded:
        chunks = []

    logger.debug(
        f"Retrieved {len(chunks)} chunks | grounded={is_grounded} | "
        f"best={best:.3f} | query='{query[:60]}...'"
    )
    return chunks, is_grounded


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
