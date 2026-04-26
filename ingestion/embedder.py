"""
Generates embeddings using BGE-small model and upserts to Qdrant.
BGE-small runs locally — no API costs, no rate limits.
"""

import time

from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    VectorParams,
    Distance,
    PayloadSchemaType,
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
            timeout=120,  # generous timeout for large batch upserts
        )
    return _qdrant


def ensure_collection_exists() -> None:
    """Creates the Qdrant collection if it doesn't exist yet."""
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
        client.create_payload_index(
            settings.qdrant_collection, "category", PayloadSchemaType.KEYWORD
        )
        client.create_payload_index(
            settings.qdrant_collection, "circular_id", PayloadSchemaType.KEYWORD
        )
        client.create_payload_index(
            settings.qdrant_collection, "doc_name", PayloadSchemaType.KEYWORD
        )
        logger.success(f"Created Qdrant collection: {settings.qdrant_collection}")
    else:
        logger.info(f"Collection '{settings.qdrant_collection}' already exists")


def embed_and_store(chunks: list[dict], batch_size: int = 32) -> int:
    """
    Embeds chunk texts and upserts to Qdrant in batches.
    Returns number of vectors stored.
    """
    model = get_embedding_model()
    client = get_qdrant_client()
    ensure_collection_exists()

    total_stored = 0

    for i in tqdm(range(0, len(chunks), batch_size), desc="Embedding & storing"):
        batch = chunks[i : i + batch_size]
        texts = [c["chunk_text"] for c in batch]

        prefixed_texts = [f"passage: {t}" for t in texts]
        vectors = model.encode(prefixed_texts, normalize_embeddings=True).tolist()

        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=vector,
                payload={k: v for k, v in chunk.items() if k != "chunk_id"},
            )
            for chunk, vector in zip(batch, vectors)
        ]

        # Retry up to 3 times on transient network timeouts
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
                    logger.warning(f"Upsert attempt {attempt + 1} failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        total_stored += len(points)

    logger.success(f"Stored {total_stored} vectors in Qdrant")
    return total_stored


def embed_query(query: str) -> list[float]:
    """Embeds a single query string. Uses 'query:' prefix for BGE asymmetric search."""
    model = get_embedding_model()
    vector = model.encode(
        f"query: {query}", normalize_embeddings=True
    ).tolist()
    return vector
