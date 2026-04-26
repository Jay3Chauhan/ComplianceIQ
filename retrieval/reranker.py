"""
Optional cross-encoder reranking stage for improved precision.
Not used by default; wire into retriever.retrieve_chunks if you want reranking.
"""

from loguru import logger
from sentence_transformers import CrossEncoder

_cross_encoder: CrossEncoder | None = None

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"


def get_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        logger.info(f"Loading reranker model: {model_name}")
        _cross_encoder = CrossEncoder(model_name)
    return _cross_encoder


def rerank_chunks(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """
    Reranks the given chunks against the query using a cross-encoder.
    Attaches a 'rerank_score' field to each chunk.
    """
    if not chunks:
        return chunks

    reranker = get_reranker()
    pairs = [(query, c["chunk_text"]) for c in chunks]
    scores = reranker.predict(pairs).tolist()

    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    return reranked[:top_k]
