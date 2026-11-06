"""
Document registry (data/document_registry.json): the source of truth for
document metadata. Thread-safe read/modify/write.
"""

import json
import re
import threading
from pathlib import Path

REGISTRY_PATH = Path("data/document_registry.json")
DOCS_DIR = Path("data/documents")
CATEGORIES = ("RBI", "SEBI", "AA", "GENERAL")

_lock = threading.Lock()


def doc_id_for(filename: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-")


def safe_filename(filename: str) -> str:
    """Strips paths and unsafe characters; always ends in .pdf."""
    name = Path(filename).name
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._") or "document"
    return f"{stem[:120]}.pdf"


def _with_ids(entries: list[dict]) -> list[dict]:
    for e in entries:
        e.setdefault("doc_id", doc_id_for(e["filename"]))
    return entries


def load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    with _lock:
        return _with_ids(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def _save(entries: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


def get_entry(doc_id_or_filename: str) -> dict | None:
    for e in load_registry():
        if doc_id_or_filename in (e["doc_id"], e["filename"]):
            return e
    return None


def upsert_entry(meta: dict) -> dict:
    meta = {**meta, "doc_id": meta.get("doc_id") or doc_id_for(meta["filename"])}
    with _lock:
        entries = json.loads(REGISTRY_PATH.read_text(encoding="utf-8")) if REGISTRY_PATH.exists() else []
        entries = [e for e in entries if e["filename"] != meta["filename"]]
        entries.append({k: v for k, v in meta.items() if k != "doc_id"})
        _save(entries)
    return meta


def remove_entry(filename: str) -> bool:
    with _lock:
        if not REGISTRY_PATH.exists():
            return False
        entries = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        kept = [e for e in entries if e["filename"] != filename]
        _save(kept)
        return len(kept) != len(entries)


def pdf_path_for(entry: dict) -> Path:
    return DOCS_DIR / entry["filename"]
