"""
Document catalog: registry metadata joined with what is actually indexed.
Powers document listing, per-page passage viewing and section outlines.
"""

from qdrant_client import models

from config import settings
from ingestion.embedder import collection_exists, count_by_filename, get_qdrant_client
from ingestion.registry import get_entry, load_registry, pdf_path_for
from retrieval.cache import TTLCache

_catalog_cache = TTLCache(ttl_seconds=120, max_items=4)
_outline_cache = TTLCache(ttl_seconds=600, max_items=32)

PAGE_FIELDS = ["seq", "chunk_text", "section", "page_number", "total_pages"]


def _summary(entry: dict, chunks: int) -> dict:
    return {
        "doc_id": entry["doc_id"],
        "name": entry["name"],
        "circular_id": entry.get("circular_id", ""),
        "category": entry.get("category", "GENERAL"),
        "subcategory": entry.get("subcategory", ""),
        "date": entry.get("date", ""),
        "issuer": entry.get("issuer", ""),
        "source_url": entry.get("url", ""),
        "filename": entry["filename"],
        "has_file": pdf_path_for(entry).exists(),
        "chunks": chunks,
        "indexed": chunks > 0,
    }


def list_documents(category: str | None = None, use_cache: bool = True) -> list[dict]:
    docs = _catalog_cache.get("all") if use_cache else None
    if docs is None:
        exists = collection_exists()
        docs = [_summary(e, count_by_filename(e["filename"]) if exists else 0) for e in load_registry()]
        docs.sort(key=lambda d: (d["category"], d["name"]))
        _catalog_cache.set("all", docs)
    if category and category.upper() != "ALL":
        return [d for d in docs if d["category"] == category.upper()]
    return docs


def get_document(doc_id: str) -> dict | None:
    entry = get_entry(doc_id)
    if not entry:
        return None
    return next((d for d in list_documents() if d["doc_id"] == entry["doc_id"]), None) or _summary(entry, 0)


def _scroll(flt: models.Filter, fields: list[str]) -> list[dict]:
    client = get_qdrant_client()
    out: list[dict] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=flt,
            limit=256,
            offset=offset,
            with_payload=fields,
        )
        out.extend({**p.payload, "chunk_id": str(p.id)} for p in points)
        if offset is None:
            return out


def _file_filter(filename: str, page: int | None = None) -> models.Filter:
    must = [models.FieldCondition(key="filename", match=models.MatchValue(value=filename))]
    if page is not None:
        must.append(models.FieldCondition(key="page_number", match=models.MatchValue(value=page)))
    return models.Filter(must=must)


def get_page(doc_id: str, page_number: int) -> dict | None:
    """All indexed passages of one page, in reading order."""
    entry = get_entry(doc_id)
    if not entry:
        return None
    chunks = sorted(_scroll(_file_filter(entry["filename"], page_number), PAGE_FIELDS), key=lambda c: c["seq"])
    total = chunks[0]["total_pages"] if chunks else None
    return {
        "doc_id": entry["doc_id"],
        "name": entry["name"],
        "page_number": page_number,
        "total_pages": total,
        "passages": [
            {"chunk_id": c["chunk_id"], "seq": c["seq"], "section": c.get("section", ""), "text": c["chunk_text"]}
            for c in chunks
        ],
    }


def get_outline(doc_id: str) -> dict | None:
    """Distinct sections in reading order with their first page."""
    entry = get_entry(doc_id)
    if not entry:
        return None
    cached = _outline_cache.get(entry["doc_id"])
    if cached is not None:
        return cached
    chunks = sorted(_scroll(_file_filter(entry["filename"]), ["seq", "section", "page_number"]), key=lambda c: c["seq"])
    sections: list[dict] = []
    for c in chunks:
        label = c.get("section") or ""
        if label and (not sections or sections[-1]["section"] != label):
            sections.append({"section": label, "page_number": c["page_number"], "passages": 1})
        elif sections and sections[-1]["section"] == label:
            sections[-1]["passages"] += 1
    outline = {"doc_id": entry["doc_id"], "name": entry["name"], "sections": sections}
    _outline_cache.set(entry["doc_id"], outline)
    return outline


def collection_stats() -> dict:
    client = get_qdrant_client()
    info = client.get_collection(settings.qdrant_collection)
    return {
        "collection": settings.qdrant_collection,
        "points": info.points_count or 0,
        "status": str(info.status.value if hasattr(info.status, "value") else info.status),
        "indexed_vectors": info.indexed_vectors_count or 0,
    }
