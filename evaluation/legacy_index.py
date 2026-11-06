"""
Frozen copy of the v1 ingestion (raw page text, 900/120 recursive split, no
prefixes, dense-only) as a local exact-search index. Used only as the baseline
in evaluation so v2 improvements are measured, not assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from ingestion.embedder import get_dense_model

CACHE_DIR = Path(__file__).parent / ".cache"
REGISTRY_PATH = Path("data/document_registry.json")
DOCS_DIR = Path("data/documents")

_chunks: list[dict] | None = None
_matrix: np.ndarray | None = None


def _v1_chunks() -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
        separators=["\n\n\n", "\n\n", "\nChapter ", "\nSection ", "\nClause ", "\n", "। ", ". ", " ", ""],
    )
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    chunks: list[dict] = []
    for meta in registry:
        path = DOCS_DIR / meta["filename"]
        if not path.exists():
            continue
        with pymupdf.open(path) as doc:
            for i, page in enumerate(doc):
                text = "\n".join(l.strip() for l in page.get_text("text").split("\n") if l.strip())
                for piece in splitter.split_text(text):
                    if len(piece.strip()) < 50:
                        continue
                    chunks.append({
                        "chunk_text": piece.strip(),
                        "page_number": i + 1,
                        "filename": meta["filename"],
                        "doc_name": meta["name"],
                        "category": meta["category"],
                    })
    return chunks


def load() -> tuple[list[dict], np.ndarray]:
    global _chunks, _matrix
    if _chunks is not None and _matrix is not None:
        return _chunks, _matrix

    CACHE_DIR.mkdir(exist_ok=True)
    chunks_path = CACHE_DIR / "legacy_chunks.json"
    matrix_path = CACHE_DIR / "legacy_dense.npy"
    if chunks_path.exists() and matrix_path.exists():
        _chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        _matrix = np.load(matrix_path)
    else:
        logger.info("Building legacy baseline index (one-off)…")
        _chunks = _v1_chunks()
        _matrix = get_dense_model().encode(
            [c["chunk_text"] for c in _chunks],
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=True,
        ).astype(np.float32)
        chunks_path.write_text(json.dumps(_chunks), encoding="utf-8")
        np.save(matrix_path, _matrix)
        logger.info(f"Legacy index: {len(_chunks)} chunks")
    return _chunks, _matrix


def search(query: str, limit: int, category: str | None = None) -> list[dict]:
    chunks, matrix = load()
    q = get_dense_model().encode(query, normalize_embeddings=True).astype(np.float32)
    scores = matrix @ q
    if category and category != "ALL":
        mask = np.array([c["category"] == category for c in chunks])
        scores = np.where(mask, scores, -1.0)
    top = np.argsort(-scores)[:limit]
    return [{**chunks[i], "dense_score": float(scores[i])} for i in top]
