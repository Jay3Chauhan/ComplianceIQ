"""
Dense (BGE) + sparse (BM25) embeddings and Qdrant storage.

Collection layout (hybrid):
  vectors:        "dense" → 384-d cosine (BAAI/bge-small-en-v1.5)
  sparse vectors: "bm25"  → BM25 term weights with server-side IDF
"""

import threading
import time
from collections.abc import Iterable

from fastembed import SparseTextEmbedding
from loguru import logger
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import settings

_dense: SentenceTransformer | None = None
_sparse: SparseTextEmbedding | None = None
_qdrant: QdrantClient | None = None
_lock = threading.Lock()

KEYWORD_INDEXES = ("category", "filename", "doc_id", "circular_id")
INTEGER_INDEXES = ("page_number", "seq")


def get_dense_model() -> SentenceTransformer:
    global _dense
    if _dense is None:
        with _lock:
            if _dense is None:
                logger.info(f"Loading dense model: {settings.embedding_model}")
                _dense = SentenceTransformer(settings.embedding_model)
    return _dense


def get_sparse_model() -> SparseTextEmbedding:
    global _sparse
    if _sparse is None:
        with _lock:
            if _sparse is None:
                logger.info(f"Loading sparse model: {settings.sparse_model}")
                _sparse = SparseTextEmbedding(settings.sparse_model)
    return _sparse


def get_qdrant_client() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=120,
        )
    return _qdrant


def embed_dense_documents(texts: list[str]) -> list[list[float]]:
    return get_dense_model().encode(
        texts, normalize_embeddings=True, batch_size=32
    ).tolist()


def embed_dense_query(query: str) -> list[float]:
    return get_dense_model().encode(
        settings.query_instruction + query, normalize_embeddings=True
    ).tolist()


def embed_sparse_documents(texts: list[str]) -> list[models.SparseVector]:
    return [
        models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
        for e in get_sparse_model().embed(texts, batch_size=32)
    ]


def embed_sparse_query(query: str) -> models.SparseVector:
    e = next(iter(get_sparse_model().query_embed(query)))
    return models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())


def collection_exists(name: str | None = None) -> bool:
    name = name or settings.qdrant_collection
    return name in {c.name for c in get_qdrant_client().get_collections().collections}


def ensure_collection_exists() -> None:
    """Creates the hybrid collection and payload indexes if missing."""
    client = get_qdrant_client()
    name = settings.qdrant_collection
    if not collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config={
                settings.dense_vector_name: models.VectorParams(
                    size=settings.embedding_dim, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                settings.sparse_vector_name: models.SparseVectorParams(
                    modifier=models.Modifier.IDF
                )
            },
        )
        logger.success(f"Created hybrid collection: {name}")

        for field in KEYWORD_INDEXES:
            client.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
        for field in INTEGER_INDEXES:
            client.create_payload_index(name, field, models.PayloadSchemaType.INTEGER)


def delete_by_filename(filename: str) -> None:
    """Removes all vectors for one source PDF (idempotent re-ingest)."""
    if not filename or not collection_exists():
        return
    get_qdrant_client().delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="filename", match=models.MatchValue(value=filename))]
            )
        ),
        wait=True,
    )
    logger.info(f"Deleted existing vectors for {filename}")


def count_by_filename(filename: str) -> int:
    return get_qdrant_client().count(
        collection_name=settings.qdrant_collection,
        count_filter=models.Filter(
            must=[models.FieldCondition(key="filename", match=models.MatchValue(value=filename))]
        ),
        exact=True,
    ).count


def _batches(items: list[dict], size: int) -> Iterable[list[dict]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def embed_and_store(
    chunks: list[dict],
    batch_size: int = 32,
    replace_existing: bool = True,
    show_progress: bool = True,
) -> int:
    """
    Embeds chunks (dense + sparse) and upserts them.
    Each chunk must carry `chunk_id`, `embed_text` and payload fields.
    """
    if not chunks:
        return 0

    ensure_collection_exists()
    client = get_qdrant_client()
    if replace_existing:
        delete_by_filename(chunks[0].get("filename", ""))

    batches = list(_batches(chunks, batch_size))
    iterator = tqdm(batches, desc="Embedding & storing") if show_progress else batches
    stored = 0

    for batch in iterator:
        texts = [c["embed_text"] for c in batch]
        dense = embed_dense_documents(texts)
        sparse = embed_sparse_documents(texts)
        points = [
            models.PointStruct(
                id=c["chunk_id"],
                vector={
                    settings.dense_vector_name: d,
                    settings.sparse_vector_name: s,
                },
                payload={k: v for k, v in c.items() if k not in ("chunk_id", "embed_text")},
            )
            for c, d, s in zip(batch, dense, sparse)
        ]
        for attempt in range(3):
            try:
                client.upsert(collection_name=settings.qdrant_collection, points=points)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                wait = 5 * (attempt + 1)
                logger.warning(f"Upsert failed ({e}); retrying in {wait}s")
                time.sleep(wait)
        stored += len(points)

    logger.success(f"Stored {stored} vectors in {settings.qdrant_collection}")
    return stored
