"""
Generates embeddings using BGE-small and upserts to Qdrant.
Supports idempotent re-ingest (delete by filename before upsert).
"""

import time

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
    PayloadSchemaType,
    Filter,
    FieldCondition,
    MatchValue,
)
from tqdm import tqdm
from loguru import logger
from config import settings


_model: SentenceTransformer | None = None
_qdrant: QdrantClient | None = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def get_qdrant_client() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=120,
        )
    return _qdrant


def ensure_collection_exists() -> None:
    """Creates the Qdrant collection and payload indexes if needed."""
    client = get_qdrant_client()
    existing = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        logger.success(f"Created Qdrant collection: {settings.qdrant_collection}")
    else:
        logger.info(f"Collection '{settings.qdrant_collection}' already exists")

    for field in ("category", "circular_id", "doc_name", "filename"):
        try:
            client.create_payload_index(
                settings.qdrant_collection, field, PayloadSchemaType.KEYWORD
            )
        except Exception:
            # Index may already exist
            pass


def delete_by_filename(filename: str) -> None:
    """Removes all vectors for a given source PDF (idempotent re-ingest)."""
    if not filename:
        return
    client = get_qdrant_client()
    ensure_collection_exists()
    try:
        client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
            ),
        )
        logger.info(f"Deleted existing vectors for filename={filename}")
    except Exception as e:
        logger.warning(f"Delete-by-filename skipped: {e}")


def embed_and_store(
    chunks: list[dict],
    batch_size: int = 32,
    replace_existing: bool = True,
) -> int:
    """
    Embeds chunk texts and upserts to Qdrant in batches.
    When replace_existing=True, deletes prior vectors for the same filename first.
    """
    if not chunks:
        return 0

    model = get_embedding_model()
    client = get_qdrant_client()
    ensure_collection_exists()

    if replace_existing:
        filename = chunks[0].get("filename", "")
        if filename:
            delete_by_filename(filename)

    total_stored = 0

    for i in tqdm(range(0, len(chunks), batch_size), desc="Embedding & storing"):
        batch = chunks[i : i + batch_size]
        texts = [c["chunk_text"] for c in batch]
        # bge-small-en-v1.5 does not use query/passage instruction prefixes
        vectors = model.encode(texts, normalize_embeddings=True).tolist()

        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=vector,
                payload={k: v for k, v in chunk.items() if k != "chunk_id"},
            )
            for chunk, vector in zip(batch, vectors)
        ]

        for attempt in range(3):
            try:
                client.upsert(
                    collection_name=settings.qdrant_collection,
                    points=points,
                )
                break
            except Exception as e:
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    logger.warning(
                        f"Upsert attempt {attempt + 1} failed ({e}), retrying in {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise
        total_stored += len(points)

    logger.success(f"Stored {total_stored} vectors in Qdrant")
    return total_stored


def embed_query(query: str) -> list[float]:
    """Embeds a single query string for dense retrieval."""
    model = get_embedding_model()
    return model.encode(query, normalize_embeddings=True).tolist()
