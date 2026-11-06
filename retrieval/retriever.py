"""
Retrieval v2: hybrid (dense BGE + sparse BM25, fused with RRF) → cross-encoder
rerank → grounding gate → per-page diversity.

The gate is what keeps the assistant from answering out-of-corpus questions:
if the best reranked passage is not convincingly relevant, the result is marked
not grounded and the generator refuses instead of improvising.
"""

import time
from dataclasses import dataclass, field

import numpy as np
from loguru import logger
from qdrant_client import models

from config import settings
from ingestion.chunker import build_embed_text
from ingestion.embedder import embed_dense_query, embed_sparse_query, get_qdrant_client
from retrieval.cache import TTLCache
from retrieval.glossary import expand_query
from retrieval.reranker import rerank_chunks

STRATEGIES = ("hybrid", "dense", "sparse")
_cache = TTLCache(ttl_seconds=settings.retrieval_cache_ttl, max_items=256)


@dataclass
class RetrievalResult:
    query: str
    search_query: str
    chunks: list[dict]
    is_grounded: bool
    gate_score: float
    strategy: str
    reranked: bool
    candidates: int
    timings: dict[str, float] = field(default_factory=dict)
    cached: bool = False


def _category_filter(category: str | None) -> models.Filter | None:
    if not category or category.upper() == "ALL":
        return None
    return models.Filter(
        must=[models.FieldCondition(key="category", match=models.MatchValue(value=category.upper()))]
    )


def _search(
    search_query: str,
    strategy: str,
    limit: int,
    flt: models.Filter | None,
    collection: str,
    with_dense_vectors: bool,
) -> tuple[list[dict], list[float] | None]:
    client = get_qdrant_client()
    dense_name, sparse_name = settings.dense_vector_name, settings.sparse_vector_name
    dense_vec = embed_dense_query(search_query) if strategy in ("hybrid", "dense") else None
    sparse_vec = embed_sparse_query(search_query) if strategy in ("hybrid", "sparse") else None
    with_vectors = [dense_name] if with_dense_vectors else False

    if strategy == "hybrid":
        res = client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(query=dense_vec, using=dense_name, limit=settings.prefetch_limit, filter=flt),
                models.Prefetch(query=sparse_vec, using=sparse_name, limit=settings.prefetch_limit, filter=flt),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
            with_payload=True,
            with_vectors=with_vectors,
        )
    else:
        res = client.query_points(
            collection_name=collection,
            query=dense_vec if strategy == "dense" else sparse_vec,
            using=dense_name if strategy == "dense" else sparse_name,
            query_filter=flt,
            limit=limit,
            with_payload=True,
            with_vectors=with_vectors,
        )

    chunks = []
    for p in res.points:
        chunk = {**p.payload, "chunk_id": str(p.id), "retrieval_score": round(float(p.score), 4)}
        if with_dense_vectors and p.vector and dense_vec is not None:
            vec = p.vector.get(dense_name) if isinstance(p.vector, dict) else p.vector
            chunk["dense_score"] = round(float(np.dot(vec, dense_vec)), 4)
        chunks.append(chunk)
    return chunks, dense_vec


def _diversify(chunks: list[dict], top_k: int) -> list[dict]:
    """Caps chunks per page and drops near-duplicate passages (chunk overlap)."""
    picked: list[dict] = []
    per_page: dict[tuple[str, int], int] = {}
    for c in chunks:
        key = (c.get("filename", ""), c.get("page_number", 0))
        if per_page.get(key, 0) >= settings.max_chunks_per_page:
            continue
        head = c["chunk_text"][:160]
        if any(head in p["chunk_text"] or p["chunk_text"][:160] in c["chunk_text"] for p in picked):
            continue
        per_page[key] = per_page.get(key, 0) + 1
        picked.append(c)
        if len(picked) >= top_k:
            break
    return picked


def retrieve(
    query: str,
    top_k: int | None = None,
    category: str | None = None,
    strategy: str | None = None,
    rerank: bool | None = None,
    collection: str | None = None,
    use_cache: bool = True,
    apply_gate: bool = True,
) -> RetrievalResult:
    """
    Retrieves the most relevant chunks for `query`.

    With apply_gate=True, chunks are emptied when the result is not grounded so
    callers cannot accidentally pass weak context to the LLM.
    """
    top_k = top_k or settings.max_retrieval_chunks
    strategy = strategy or settings.retrieval_strategy
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'")
    rerank = settings.enable_rerank if rerank is None else rerank
    collection = collection or settings.qdrant_collection

    cache_key = (query, top_k, (category or "ALL").upper(), strategy, rerank, collection, apply_gate)
    if use_cache and (hit := _cache.get(cache_key)) is not None:
        return RetrievalResult(**{**hit.__dict__, "cached": True})

    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    search_query = expand_query(query) if settings.enable_glossary_expansion else query
    n_candidates = settings.rerank_candidates if rerank else top_k * 3

    candidates, _ = _search(
        search_query, strategy, n_candidates, _category_filter(category), collection,
        with_dense_vectors=not rerank and strategy != "sparse",
    )
    timings["search_ms"] = round((time.perf_counter() - t0) * 1000)

    if rerank and candidates:
        t1 = time.perf_counter()
        for c in candidates:
            c["embed_text"] = build_embed_text(c.get("doc_name", ""), c.get("section", ""), c["chunk_text"])
        candidates = rerank_chunks(search_query, candidates)
        for c in candidates:
            c.pop("embed_text", None)
        timings["rerank_ms"] = round((time.perf_counter() - t1) * 1000)
        gate_score = candidates[0]["rerank_score"]
        grounded = gate_score >= settings.rerank_min_score
        if grounded:
            floor = max(settings.relative_score_floor, gate_score * 0.02)
            candidates = [c for c in candidates if c["rerank_score"] >= floor] or candidates[:1]
    else:
        gate_score = max((c.get("dense_score", 0.0) for c in candidates), default=0.0)
        grounded = bool(candidates) and gate_score >= settings.dense_min_score
        if strategy == "sparse":
            grounded = bool(candidates)

    chunks = _diversify(candidates, top_k)
    for c in chunks:
        c["relevance_score"] = c.get("rerank_score", c.get("dense_score", c.get("retrieval_score", 0.0)))

    if apply_gate and not grounded:
        chunks = []

    timings["total_ms"] = round((time.perf_counter() - t0) * 1000)
    result = RetrievalResult(
        query=query,
        search_query=search_query,
        chunks=chunks,
        is_grounded=grounded,
        gate_score=round(float(gate_score), 4),
        strategy=strategy,
        reranked=rerank,
        candidates=len(candidates),
        timings=timings,
    )
    logger.debug(
        f"retrieve[{strategy}{'+rerank' if rerank else ''}] grounded={grounded} "
        f"gate={result.gate_score} chunks={len(chunks)} {timings}"
    )
    if use_cache:
        _cache.set(cache_key, result)
    return result


def retrieve_chunks(
    query: str,
    top_k: int | None = None,
    category_filter: str | None = None,
    enable_rerank: bool | None = None,
) -> tuple[list[dict], bool]:
    """Backward-compatible wrapper used by legacy routes: (chunks, is_grounded)."""
    result = retrieve(query, top_k=top_k, category=category_filter, rerank=enable_rerank)
    return result.chunks, result.is_grounded
