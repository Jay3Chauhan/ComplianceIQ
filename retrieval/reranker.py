"""
Cross-encoder reranking. Scores are probabilities in [0, 1] (sigmoid applied for
every model) and drive both ordering and the grounding gate, because they are
far better calibrated than fused RRF scores or raw cosine similarity.
"""

import threading

import torch
from loguru import logger
from sentence_transformers import CrossEncoder

from config import settings

_cross_encoder: CrossEncoder | None = None
_lock = threading.Lock()


def get_reranker() -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        with _lock:
            if _cross_encoder is None:
                logger.info(f"Loading reranker: {settings.reranker_model}")
                _cross_encoder = CrossEncoder(
                    settings.reranker_model,
                    max_length=384,
                    activation_fn=torch.nn.Sigmoid(),
                )
    return _cross_encoder


def rerank_chunks(query: str, chunks: list[dict], top_k: int | None = None) -> list[dict]:
    """Scores (query, chunk) pairs, attaches `rerank_score`, returns chunks best-first."""
    if not chunks:
        return chunks
    pairs = [(query, c.get("embed_text") or c["chunk_text"]) for c in chunks]
    scores = get_reranker().predict(pairs, batch_size=16, show_progress_bar=False)
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = round(float(score), 4)
    ranked = sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)
    return ranked[:top_k] if top_k else ranked
