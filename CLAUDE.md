# ComplianceIQ — RBI/SEBI Regulatory RAG Bot
## Master Build Instructions (CLAUDE.md)

> Feed this entire file to Claude Code, Cursor, or any AI coding assistant.
> It contains every instruction needed to build the full project from scratch.

---

## PROJECT OVERVIEW

Build **ComplianceIQ** — a production-grade RAG (Retrieval-Augmented Generation) system that:
- Ingests RBI Master Directions, SEBI circulars, AA Framework guidelines as PDFs
- Embeds them into a Qdrant vector database with rich metadata
- Answers compliance questions in natural language using Groq (LLaMA 3.3 70B)
- Returns grounded answers with exact circular references, section numbers, and page citations
- Exposes a FastAPI REST backend and a Streamlit chat frontend

**Tech Stack:**
- LLM: Groq API (`llama-3.3-70b-versatile`) — free tier
- Embeddings: `BAAI/bge-small-en-v1.5` via sentence-transformers — local, free
- Vector DB: Qdrant Cloud — free cluster
- Framework: LangChain + FastAPI
- Frontend: Streamlit
- PDF parsing: PyMuPDF (fitz) + pdfplumber
- Evaluation: RAGAS
- Hosting: Render (API) + Streamlit Cloud (UI)

---

## ENVIRONMENT VARIABLES

Create a `.env` file in the project root with these keys:

```env
# Groq — get free key at https://console.groq.com
GROQ_API_KEY=your_groq_api_key_here

# Qdrant Cloud — get from https://cloud.qdrant.io
QDRANT_URL=https://YOUR-CLUSTER-ID.us-west-1-0.aws.cloud.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_api_key_here

# Collection name in Qdrant
QDRANT_COLLECTION=regulations

# Embedding model
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384

# Groq model
GROQ_MODEL=llama-3.3-70b-versatile

# App settings
APP_ENV=development
LOG_LEVEL=INFO
MAX_RETRIEVAL_CHUNKS=5
CHUNK_SIZE=500
CHUNK_OVERLAP=50
```

**NEVER commit `.env` to git. It is already in `.gitignore`.**

---

## EXACT FOLDER STRUCTURE

Create this exact folder and file structure. Do not deviate:

```
complianceiq/
├── .env                          # env vars — never commit
├── .gitignore
├── README.md
├── requirements.txt
├── config.py                     # central config from env vars
│
├── data/
│   ├── documents/                # raw PDFs go here (gitignored)
│   └── document_registry.json   # metadata for all ingested docs
│
├── ingestion/
│   ├── __init__.py
│   ├── pdf_parser.py             # PyMuPDF text extraction
│   ├── chunker.py                # text splitting with metadata
│   ├── embedder.py               # BGE embeddings + Qdrant upsert
│   └── run_ingestion.py          # CLI script: python -m ingestion.run_ingestion
│
├── retrieval/
│   ├── __init__.py
│   ├── retriever.py              # Qdrant similarity search
│   └── reranker.py               # cross-encoder reranking (optional)
│
├── llm/
│   ├── __init__.py
│   ├── groq_client.py            # Groq API wrapper
│   └── prompt_templates.py      # all system prompts
│
├── api/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app entry point
│   ├── models.py                 # Pydantic request/response schemas
│   └── routes/
│       ├── __init__.py
│       ├── query.py              # POST /api/query
│       ├── ingest.py             # POST /api/ingest (admin)
│       └── documents.py          # GET /api/documents
│
├── frontend/
│   └── app.py                    # Streamlit chat UI
│
├── evaluation/
│   ├── __init__.py
│   ├── ragas_eval.py             # RAGAS evaluation pipeline
│   └── test_questions.json      # 20 sample Q&A pairs for eval
│
└── tests/
    ├── __init__.py
    ├── test_ingestion.py
    ├── test_retrieval.py
    └── test_api.py
```

---

## FILE: `.gitignore`

```gitignore
.env
__pycache__/
*.pyc
*.pyo
.pytest_cache/
venv/
.venv/
data/documents/
*.pdf
.DS_Store
*.log
```

---

## FILE: `requirements.txt`

```txt
# LLM & RAG
langchain==0.3.7
langchain-groq==0.2.1
langchain-community==0.3.7
langchain-core==0.3.15
groq==0.11.0

# Vector DB
qdrant-client==1.12.0

# Embeddings
sentence-transformers==3.3.1
torch==2.4.0

# PDF Parsing
PyMuPDF==1.24.13
pdfplumber==0.11.4

# API
fastapi==0.115.4
uvicorn[standard]==0.32.0
python-multipart==0.0.12
pydantic==2.9.2
pydantic-settings==2.6.0

# Utilities
python-dotenv==1.0.1
httpx==0.27.2
loguru==0.7.2
tqdm==4.67.0

# Frontend
streamlit==1.40.1

# Evaluation
ragas==0.2.6
datasets==3.1.0

# Testing
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

---

## FILE: `config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str = "regulations"

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # RAG settings
    max_retrieval_chunks: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 50

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

---

## FILE: `data/document_registry.json`

This file defines all documents to ingest. Add more documents here as you collect PDFs.

```json
[
  {
    "filename": "RBI_KYC_Master_Direction_2016.pdf",
    "name": "RBI Master Direction on KYC 2016",
    "circular_id": "RBI/DBR.AML.BC.No.81/14.01.001/2015-16",
    "category": "RBI",
    "subcategory": "KYC",
    "date": "2016-02-25",
    "issuer": "Reserve Bank of India",
    "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=11566"
  },
  {
    "filename": "RBI_Digital_Lending_Guidelines_2022.pdf",
    "name": "RBI Guidelines on Digital Lending 2022",
    "circular_id": "RBI/2022-23/111",
    "category": "RBI",
    "subcategory": "Digital Lending",
    "date": "2022-09-02",
    "issuer": "Reserve Bank of India",
    "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=12382"
  },
  {
    "filename": "RBI_Account_Aggregator_Master_Direction.pdf",
    "name": "RBI Master Direction on Account Aggregator Framework",
    "circular_id": "RBI/DNBR/2016-17/46",
    "category": "AA",
    "subcategory": "Account Aggregator",
    "date": "2016-09-02",
    "issuer": "Reserve Bank of India",
    "url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10598"
  },
  {
    "filename": "SEBI_Stock_Broker_Master_Circular_2023.pdf",
    "name": "SEBI Master Circular for Stock Brokers 2023",
    "circular_id": "SEBI/HO/MIRSD/MIRSD-PoD-1/P/CIR/2023/67",
    "category": "SEBI",
    "subcategory": "Stock Brokers",
    "date": "2023-05-17",
    "issuer": "Securities and Exchange Board of India",
    "url": "https://www.sebi.gov.in/legal/circulars/may-2023/master-circular-for-stock-brokers_71868.html"
  },
  {
    "filename": "SEBI_Mutual_Funds_Master_Circular_2024.pdf",
    "name": "SEBI Master Circular for Mutual Funds 2024",
    "circular_id": "SEBI/HO/IMD/IMD-PoD-1/P/CIR/2024/14",
    "category": "SEBI",
    "subcategory": "Mutual Funds",
    "date": "2024-02-15",
    "issuer": "Securities and Exchange Board of India",
    "url": "https://www.sebi.gov.in"
  },
  {
    "filename": "ReBIT_AA_Technical_Specifications.pdf",
    "name": "ReBIT Account Aggregator Technical Specifications v2.0",
    "circular_id": "ReBIT/AA/TECH/2023",
    "category": "AA",
    "subcategory": "Technical",
    "date": "2023-01-01",
    "issuer": "ReBIT",
    "url": "https://rebit.org.in"
  }
]
```

---

## FILE: `ingestion/pdf_parser.py`

```python
"""
PDF text extraction using PyMuPDF.
Preserves page structure and extracts metadata per page.
"""

import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from loguru import logger
from typing import Optional


def extract_with_pymupdf(pdf_path: str) -> list[dict]:
    """
    Primary extraction using PyMuPDF.
    Returns list of page dicts with text and page number.
    """
    pages = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            # Clean up excessive whitespace
            text = "\n".join(
                line.strip() for line in text.split("\n") if line.strip()
            )
            if text:
                pages.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "total_pages": len(doc)
                })
        doc.close()
        logger.info(f"PyMuPDF extracted {len(pages)} pages from {pdf_path}")
    except Exception as e:
        logger.error(f"PyMuPDF extraction failed for {pdf_path}: {e}")
        return extract_with_pdfplumber(pdf_path)
    return pages


def extract_with_pdfplumber(pdf_path: str) -> list[dict]:
    """
    Fallback extraction using pdfplumber.
    Better for tables and complex layouts.
    """
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = "\n".join(
                    line.strip() for line in text.split("\n") if line.strip()
                )
                if text:
                    pages.append({
                        "page_number": page_num + 1,
                        "text": text,
                        "total_pages": len(pdf.pages)
                    })
        logger.info(f"pdfplumber extracted {len(pages)} pages from {pdf_path}")
    except Exception as e:
        logger.error(f"pdfplumber extraction also failed for {pdf_path}: {e}")
    return pages


def parse_pdf(pdf_path: str, doc_metadata: dict) -> list[dict]:
    """
    Main entry point. Parses a PDF and attaches document metadata to each page.
    
    Args:
        pdf_path: Path to the PDF file
        doc_metadata: Dict with keys: name, circular_id, category, subcategory, date, issuer
    
    Returns:
        List of page dicts, each with text + full metadata
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = extract_with_pymupdf(pdf_path)

    # Attach document metadata to every page
    enriched_pages = []
    for page in pages:
        enriched_pages.append({
            **page,
            "doc_name": doc_metadata["name"],
            "circular_id": doc_metadata.get("circular_id", ""),
            "category": doc_metadata.get("category", "GENERAL"),
            "subcategory": doc_metadata.get("subcategory", ""),
            "date": doc_metadata.get("date", ""),
            "issuer": doc_metadata.get("issuer", ""),
            "filename": doc_metadata.get("filename", ""),
            "source_url": doc_metadata.get("url", ""),
        })

    return enriched_pages
```

---

## FILE: `ingestion/chunker.py`

```python
"""
Text chunking with metadata preservation.
Splits pages into overlapping chunks for optimal RAG retrieval.
"""

import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger
from config import settings


def create_chunks(pages: list[dict]) -> list[dict]:
    """
    Splits page-level text into smaller chunks for embedding.
    Each chunk inherits full metadata from its parent page.
    
    Returns list of chunk dicts ready for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "। ", ". ", " ", ""],  # includes Hindi sentence sep
        length_function=len,
    )

    chunks = []
    for page in pages:
        if not page["text"].strip():
            continue

        text_chunks = splitter.split_text(page["text"])

        for idx, chunk_text in enumerate(text_chunks):
            if len(chunk_text.strip()) < 50:  # skip tiny chunks
                continue

            chunk = {
                "chunk_id": str(uuid.uuid4()),
                "chunk_text": chunk_text.strip(),
                "chunk_index": idx,
                "total_chunks_on_page": len(text_chunks),
                # Inherit all page metadata
                "page_number": page["page_number"],
                "total_pages": page["total_pages"],
                "doc_name": page["doc_name"],
                "circular_id": page["circular_id"],
                "category": page["category"],
                "subcategory": page["subcategory"],
                "date": page["date"],
                "issuer": page["issuer"],
                "filename": page["filename"],
                "source_url": page["source_url"],
                # Display label for citations
                "citation": f"{page['doc_name']} | {page['circular_id']} | Page {page['page_number']}",
            }
            chunks.append(chunk)

    logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")
    return chunks
```

---

## FILE: `ingestion/embedder.py`

```python
"""
Generates embeddings using BGE-small model and upserts to Qdrant.
BGE-small runs locally — no API costs, no rate limits.
"""

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


# Singleton model — loaded once, reused
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
        )
    return _qdrant


def ensure_collection_exists():
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
        # Create payload indexes for fast filtering
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


def embed_and_store(chunks: list[dict], batch_size: int = 64) -> int:
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

        # BGE models work best with this prefix for retrieval
        prefixed_texts = [f"passage: {t}" for t in texts]
        vectors = model.encode(prefixed_texts, normalize_embeddings=True).tolist()

        points = [
            PointStruct(
                id=chunk["chunk_id"],
                vector=vector,
                payload={
                    k: v for k, v in chunk.items() if k != "chunk_id"
                },
            )
            for chunk, vector in zip(batch, vectors)
        ]

        client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
        )
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
```

---

## FILE: `ingestion/run_ingestion.py`

```python
"""
CLI script to ingest PDFs into Qdrant.
Usage: python -m ingestion.run_ingestion
       python -m ingestion.run_ingestion --file data/documents/specific.pdf
       python -m ingestion.run_ingestion --category RBI
"""

import json
import argparse
from pathlib import Path
from loguru import logger
from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store


REGISTRY_PATH = "data/document_registry.json"
DOCS_DIR = "data/documents"


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def ingest_document(doc_meta: dict) -> dict:
    """Ingests a single document. Returns stats."""
    pdf_path = Path(DOCS_DIR) / doc_meta["filename"]

    if not pdf_path.exists():
        logger.warning(f"PDF not found, skipping: {pdf_path}")
        return {"status": "skipped", "reason": "file not found"}

    logger.info(f"Ingesting: {doc_meta['name']}")

    pages = parse_pdf(str(pdf_path), doc_meta)
    chunks = create_chunks(pages)
    stored = embed_and_store(chunks)

    return {
        "status": "success",
        "doc_name": doc_meta["name"],
        "pages": len(pages),
        "chunks": len(chunks),
        "vectors_stored": stored,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into ComplianceIQ")
    parser.add_argument("--category", help="Filter by category: RBI, SEBI, AA")
    parser.add_argument("--file", help="Ingest a specific filename from the registry")
    args = parser.parse_args()

    registry = load_registry()

    if args.file:
        registry = [d for d in registry if d["filename"] == args.file]
    elif args.category:
        registry = [d for d in registry if d["category"] == args.category.upper()]

    logger.info(f"Starting ingestion of {len(registry)} documents")
    results = []

    for doc in registry:
        result = ingest_document(doc)
        results.append(result)

    # Summary
    success = [r for r in results if r.get("status") == "success"]
    logger.success(
        f"Ingestion complete: {len(success)}/{len(results)} documents | "
        f"{sum(r.get('chunks', 0) for r in success)} total chunks stored"
    )


if __name__ == "__main__":
    main()
```

---

## FILE: `retrieval/retriever.py`

```python
"""
Retrieves relevant document chunks from Qdrant using vector similarity search.
Supports category filtering, date filtering, and configurable top-k.
"""

from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from loguru import logger
from ingestion.embedder import get_qdrant_client, embed_query
from config import settings


def retrieve_chunks(
    query: str,
    top_k: int = None,
    category_filter: str = None,  # "RBI", "SEBI", "AA", or None for all
    score_threshold: float = 0.35,
) -> list[dict]:
    """
    Retrieves top-k most relevant chunks for a query.

    Args:
        query: User's natural language question
        top_k: Number of chunks to retrieve (default from settings)
        category_filter: Optional filter by document category
        score_threshold: Minimum cosine similarity score (0-1)

    Returns:
        List of chunk dicts with payload + score, sorted by relevance
    """
    if top_k is None:
        top_k = settings.max_retrieval_chunks

    client = get_qdrant_client()
    query_vector = embed_query(query)

    # Build optional filter
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

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        limit=top_k,
        query_filter=search_filter,
        score_threshold=score_threshold,
        with_payload=True,
    )

    chunks = []
    for result in results:
        chunk = {**result.payload, "relevance_score": round(result.score, 4)}
        chunks.append(chunk)

    logger.debug(f"Retrieved {len(chunks)} chunks for query: '{query[:60]}...'")
    return chunks


def get_all_documents() -> list[dict]:
    """Returns metadata for all unique documents in the collection."""
    client = get_qdrant_client()

    # Scroll through all points and collect unique doc names
    seen_docs = set()
    documents = []
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
```

---

## FILE: `llm/prompt_templates.py`

```python
"""
All prompt templates for the RAG system.
These are carefully engineered to:
1. Force grounded answers (no hallucination)
2. Always include citations
3. Handle edge cases gracefully
"""

SYSTEM_PROMPT = """You are ComplianceIQ, an expert AI assistant specializing in Indian financial regulations.

Your knowledge comes EXCLUSIVELY from the regulatory documents provided in the context below.

STRICT RULES you must follow:
1. Answer ONLY based on the provided context. Never use outside knowledge.
2. Every factual claim MUST be cited with the document name, circular ID, and page number.
3. If the answer is not in the context, respond EXACTLY with: "I could not find information about this in the currently loaded regulatory documents. Please consult the relevant regulator directly or check their official website."
4. Never say "as per my knowledge" or "generally speaking" — only cite from context.
5. Format citations as: [Source: {doc_name} | {circular_id} | Page {page_number}]
6. If multiple documents are relevant, cite all of them.
7. For compliance questions, always mention if there are any penalties or consequences mentioned in the documents.
8. Keep answers structured: brief direct answer first, then details, then sources.

You are assisting compliance officers, fintech founders, and legal teams at Indian financial companies.
Be precise, professional, and legally careful in your language."""


QUERY_PROMPT_TEMPLATE = """REGULATORY CONTEXT:
{context}

---

USER QUESTION: {question}

Instructions:
- Answer based strictly on the context above
- Cite exact sources for every claim
- If unsure, say so clearly and point to the source document
- Structure: [Direct Answer] → [Details/Sub-clauses] → [Citations]"""


FOLLOWUP_PROMPT_TEMPLATE = """REGULATORY CONTEXT:
{context}

---

CONVERSATION HISTORY:
{history}

CURRENT QUESTION: {question}

Answer the current question using the regulatory context. Reference the conversation history only for context about what has already been discussed."""


def format_context(chunks: list[dict]) -> str:
    """Formats retrieved chunks into a clean context block for the LLM prompt."""
    if not chunks:
        return "No relevant regulatory documents found."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[DOCUMENT {i}]\n"
            f"Source: {chunk['doc_name']}\n"
            f"Circular: {chunk['circular_id']}\n"
            f"Category: {chunk['category']} | Page: {chunk['page_number']}\n"
            f"Date: {chunk.get('date', 'N/A')}\n"
            f"Content:\n{chunk['chunk_text']}\n"
        )

    return "\n---\n".join(context_parts)


def format_history(history: list[dict]) -> str:
    """Formats conversation history for multi-turn context."""
    if not history:
        return ""
    
    formatted = []
    for turn in history[-3:]:  # Last 3 turns only to stay within context
        formatted.append(f"User: {turn['question']}")
        formatted.append(f"Assistant: {turn['answer'][:500]}...")  # Truncate long answers
    
    return "\n".join(formatted)
```

---

## FILE: `llm/groq_client.py`

```python
"""
Groq LLM client wrapper with retry logic and error handling.
Uses llama-3.3-70b-versatile — best free model for long-context RAG.
"""

import time
from groq import Groq, RateLimitError
from loguru import logger
from config import settings
from llm.prompt_templates import (
    SYSTEM_PROMPT,
    QUERY_PROMPT_TEMPLATE,
    FOLLOWUP_PROMPT_TEMPLATE,
    format_context,
    format_history,
)


_groq_client: Groq | None = None


def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


def generate_answer(
    question: str,
    chunks: list[dict],
    history: list[dict] = None,
    max_tokens: int = 1024,
) -> dict:
    """
    Generates a grounded answer using retrieved chunks as context.

    Args:
        question: User's question
        chunks: Retrieved document chunks from Qdrant
        history: Optional conversation history (list of {question, answer})
        max_tokens: Max tokens for the response

    Returns:
        Dict with answer, sources, and token usage
    """
    client = get_groq_client()
    context = format_context(chunks)

    # Choose prompt template based on whether there's history
    if history:
        user_content = FOLLOWUP_PROMPT_TEMPLATE.format(
            context=context,
            history=format_history(history),
            question=question,
        )
    else:
        user_content = QUERY_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )

    # Retry logic for rate limits (Groq free tier: 30 req/min)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.1,  # Low temp for factual compliance answers
            )

            answer = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            # Format sources for API response
            sources = [
                {
                    "doc_name": c["doc_name"],
                    "circular_id": c["circular_id"],
                    "category": c["category"],
                    "page_number": c["page_number"],
                    "date": c.get("date", ""),
                    "source_url": c.get("source_url", ""),
                    "snippet": c["chunk_text"][:300] + "..." if len(c["chunk_text"]) > 300 else c["chunk_text"],
                    "relevance_score": c.get("relevance_score", 0),
                    "citation": c.get("citation", ""),
                }
                for c in chunks
            ]

            logger.info(f"Answer generated | tokens: {usage['total_tokens']}")
            return {
                "answer": answer,
                "sources": sources,
                "usage": usage,
                "chunks_used": len(chunks),
            }

        except RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt * 5  # 5s, 10s, 20s
                logger.warning(f"Rate limit hit. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise

        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise
```

---

## FILE: `api/models.py`

```python
"""Pydantic models for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000, description="The compliance question")
    category: Optional[Literal["ALL", "RBI", "SEBI", "AA"]] = Field(
        default="ALL", description="Filter by document category"
    )
    top_k: Optional[int] = Field(default=5, ge=1, le=10, description="Number of chunks to retrieve")
    history: Optional[list[dict]] = Field(default=None, description="Previous conversation turns")


class SourceDocument(BaseModel):
    doc_name: str
    circular_id: str
    category: str
    page_number: int
    date: str
    source_url: str
    snippet: str
    relevance_score: float
    citation: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDocument]
    chunks_used: int
    usage: dict


class IngestRequest(BaseModel):
    filename: str = Field(..., description="Filename in data/documents/ folder")


class IngestResponse(BaseModel):
    status: str
    doc_name: str
    pages: int
    chunks: int
    vectors_stored: int


class DocumentInfo(BaseModel):
    doc_name: str
    circular_id: str
    category: str
    date: str
    issuer: str
    source_url: str


class HealthResponse(BaseModel):
    status: str
    qdrant_connected: bool
    collection_name: str
    total_vectors: int
    model: str
```

---

## FILE: `api/routes/query.py`

```python
"""POST /api/query — main RAG endpoint."""

from fastapi import APIRouter, HTTPException
from loguru import logger
from api.models import QueryRequest, QueryResponse
from retrieval.retriever import retrieve_chunks
from llm.groq_client import generate_answer

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_regulations(req: QueryRequest):
    """
    Ask a compliance question. Returns a grounded answer with citations.
    
    - Retrieves top-k relevant chunks from Qdrant
    - Passes context + question to Groq LLaMA-3.3-70B
    - Returns answer with exact document citations
    """
    logger.info(f"Query received: '{req.question[:80]}...' | category={req.category}")

    try:
        # Step 1: Retrieve relevant chunks
        chunks = retrieve_chunks(
            query=req.question,
            top_k=req.top_k,
            category_filter=req.category,
        )

        if not chunks:
            return QueryResponse(
                answer="I could not find relevant information in the loaded regulatory documents for your question. Please check if the relevant documents have been ingested, or consult the regulator's official website.",
                sources=[],
                chunks_used=0,
                usage={},
            )

        # Step 2: Generate answer with Groq
        result = generate_answer(
            question=req.question,
            chunks=chunks,
            history=req.history,
        )

        return QueryResponse(**result)

    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## FILE: `api/routes/ingest.py`

```python
"""POST /api/ingest — admin endpoint to ingest documents."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from loguru import logger
from api.models import IngestRequest, IngestResponse
from ingestion.pdf_parser import parse_pdf
from ingestion.chunker import create_chunks
from ingestion.embedder import embed_and_store

router = APIRouter()

REGISTRY_PATH = "data/document_registry.json"
DOCS_DIR = "data/documents"


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(req: IngestRequest):
    """
    Ingest a PDF document into the vector store.
    The PDF must be present in data/documents/ and registered in document_registry.json.
    """
    # Find document metadata in registry
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    doc_meta = next((d for d in registry if d["filename"] == req.filename), None)

    if not doc_meta:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{req.filename}' not found in registry. Add it to document_registry.json first."
        )

    pdf_path = Path(DOCS_DIR) / req.filename
    if not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found at {pdf_path}"
        )

    try:
        pages = parse_pdf(str(pdf_path), doc_meta)
        chunks = create_chunks(pages)
        stored = embed_and_store(chunks)

        return IngestResponse(
            status="success",
            doc_name=doc_meta["name"],
            pages=len(pages),
            chunks=len(chunks),
            vectors_stored=stored,
        )
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## FILE: `api/routes/documents.py`

```python
"""GET /api/documents — list all ingested documents."""

from fastapi import APIRouter, HTTPException
from api.models import DocumentInfo, HealthResponse
from retrieval.retriever import retrieve_chunks, get_all_documents
from ingestion.embedder import get_qdrant_client
from config import settings

router = APIRouter()


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    """Returns all documents currently in the vector store."""
    try:
        return get_all_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        client = get_qdrant_client()
        collection_info = client.get_collection(settings.qdrant_collection)
        return HealthResponse(
            status="healthy",
            qdrant_connected=True,
            collection_name=settings.qdrant_collection,
            total_vectors=collection_info.points_count,
            model=settings.groq_model,
        )
    except Exception as e:
        return HealthResponse(
            status="degraded",
            qdrant_connected=False,
            collection_name=settings.qdrant_collection,
            total_vectors=0,
            model=settings.groq_model,
        )
```

---

## FILE: `api/main.py`

```python
"""
FastAPI application entry point.
Run with: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from api.routes import query, ingest, documents

app = FastAPI(
    title="ComplianceIQ API",
    description="RAG-powered Q&A for RBI/SEBI Indian regulatory documents",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(query.router, prefix="/api", tags=["Query"])
app.include_router(ingest.router, prefix="/api", tags=["Ingestion"])
app.include_router(documents.router, prefix="/api", tags=["Documents"])


@app.on_event("startup")
async def startup_event():
    logger.info("ComplianceIQ API starting up...")
    logger.info("Docs available at http://localhost:8000/docs")


@app.get("/")
async def root():
    return {
        "name": "ComplianceIQ",
        "description": "RBI/SEBI Regulatory RAG Bot",
        "docs": "/docs",
        "health": "/api/health",
    }
```

---

## FILE: `frontend/app.py`

```python
"""
Streamlit chat interface for ComplianceIQ.
Run with: streamlit run frontend/app.py
"""

import streamlit as st
import requests
import time

API_BASE = "http://localhost:8000/api"

st.set_page_config(
    page_title="ComplianceIQ",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚖️ ComplianceIQ")
st.caption("RBI · SEBI · Account Aggregator regulatory Q&A with citations")

# Sidebar
with st.sidebar:
    st.header("Settings")
    category = st.selectbox(
        "Document Category",
        ["ALL", "RBI", "SEBI", "AA"],
        help="Filter answers to a specific regulator"
    )
    top_k = st.slider("Chunks to retrieve", 3, 10, 5)
    show_sources = st.toggle("Show source documents", value=True)

    st.divider()
    st.subheader("Loaded Documents")
    try:
        docs = requests.get(f"{API_BASE}/documents", timeout=5).json()
        for doc in docs:
            badge = {"RBI": "🔵", "SEBI": "🟠", "AA": "🟢"}.get(doc["category"], "⚪")
            st.caption(f"{badge} {doc['doc_name']}")
    except Exception:
        st.caption("⚠️ Could not load document list")

    st.divider()
    if st.button("Clear conversation"):
        st.session_state.history = []
        st.rerun()

# Initialize session state
if "history" not in st.session_state:
    st.session_state.history = []

# Render chat history
for turn in st.session_state.history:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.write(turn["answer"])
        if show_sources and turn.get("sources"):
            with st.expander(f"📄 Sources ({len(turn['sources'])} documents)"):
                for src in turn["sources"]:
                    score = src.get("relevance_score", 0)
                    score_color = "green" if score > 0.7 else "orange" if score > 0.5 else "red"
                    st.markdown(
                        f"**{src['doc_name']}**  \n"
                        f"`{src['circular_id']}` · Page {src['page_number']} · "
                        f":{score_color}[Score: {score:.2f}]"
                    )
                    st.caption(src["snippet"])
                    if src.get("source_url"):
                        st.markdown(f"[View Source ↗]({src['source_url']})")
                    st.divider()

# Chat input
question = st.chat_input("Ask a compliance question... e.g. 'What are KYC norms for digital lending?'")

if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching regulatory documents..."):
            try:
                payload = {
                    "question": question,
                    "category": category,
                    "top_k": top_k,
                    "history": st.session_state.history[-3:] if st.session_state.history else None,
                }
                res = requests.post(f"{API_BASE}/query", json=payload, timeout=30).json()

                answer = res.get("answer", "No answer returned.")
                sources = res.get("sources", [])

                st.write(answer)

                if show_sources and sources:
                    with st.expander(f"📄 Sources ({len(sources)} documents)"):
                        for src in sources:
                            score = src.get("relevance_score", 0)
                            score_color = "green" if score > 0.7 else "orange" if score > 0.5 else "red"
                            st.markdown(
                                f"**{src['doc_name']}**  \n"
                                f"`{src['circular_id']}` · Page {src['page_number']} · "
                                f":{score_color}[Score: {score:.2f}]"
                            )
                            st.caption(src["snippet"])
                            if src.get("source_url"):
                                st.markdown(f"[View Source ↗]({src['source_url']})")
                            st.divider()

                st.session_state.history.append({
                    "question": question,
                    "answer": answer,
                    "sources": sources,
                })

            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to API. Make sure FastAPI is running on port 8000.")
            except Exception as e:
                st.error(f"Error: {e}")
```

---

## FILE: `README.md`

```markdown
# ComplianceIQ ⚖️
> RAG-powered Q&A for Indian financial regulations — RBI · SEBI · Account Aggregator

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Qdrant](https://img.shields.io/badge/Qdrant-Cloud-red.svg)](https://cloud.qdrant.io)

**Live Demo:** [your-streamlit-url]  
**API Docs:** [your-render-url/docs]

## What it does
Answers compliance questions grounded in actual RBI Master Directions, SEBI circulars, and AA Framework guidelines — with exact circular references, section numbers, and page citations. Zero hallucination architecture.

## Architecture
User Query → BGE Embedding → Qdrant Vector Search → LLaMA 3.3 70B (Groq) → Cited Answer

## Quick Start
```bash
# 1. Clone and setup
git clone https://github.com/yourname/complianceiq
cd complianceiq
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env with your GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY

# 3. Add PDFs to data/documents/ and run ingestion
python -m ingestion.run_ingestion

# 4. Start API
uvicorn api.main:app --reload

# 5. Start frontend (new terminal)
streamlit run frontend/app.py
```

## Stack
| Component | Technology | Cost |
|-----------|-----------|------|
| LLM | Groq LLaMA-3.3-70B | Free |
| Embeddings | BGE-small-en-v1.5 | Free (local) |
| Vector DB | Qdrant Cloud | Free tier |
| API | FastAPI | Free |
| Frontend | Streamlit | Free |

Built by Jay Chauhan — [LinkedIn](https://linkedin.com/in/yourprofile) · [Portfolio](https://jay3chauhan.github.io/Portfolio)
```

---

## STARTUP SEQUENCE (run in this exact order)

### Step 1 — Install dependencies
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Verify Qdrant connection
```bash
python -c "
from ingestion.embedder import get_qdrant_client
client = get_qdrant_client()
print(client.get_collections())
"
```

### Step 3 — Download 3 starter PDFs manually
Put them in `data/documents/` folder. Start with:
1. RBI KYC Master Direction (search rbi.org.in)
2. Any SEBI Master Circular (search sebi.gov.in)
3. RBI AA Master Direction (search rbi.org.in)

### Step 4 — Run ingestion
```bash
python -m ingestion.run_ingestion
# Or ingest only RBI docs:
python -m ingestion.run_ingestion --category RBI
```

### Step 5 — Start API
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# Test at: http://localhost:8000/docs
```

### Step 6 — Start Streamlit
```bash
streamlit run frontend/app.py
# Opens at: http://localhost:8501
```

---

## CODING RULES (follow strictly)

1. **Type hints everywhere** — all functions must have full type annotations
2. **Loguru for all logging** — no `print()` statements in production code
3. **Pydantic for all I/O** — every API request/response uses a Pydantic model
4. **Singleton clients** — embedding model and Qdrant/Groq clients are module-level singletons (loaded once)
5. **Never hardcode credentials** — all keys come from `config.settings` (from `.env`)
6. **Error handling** — all API routes use try/except with proper HTTP status codes
7. **BGE prefix convention** — always use `"passage: "` prefix for document text, `"query: "` prefix for query text when encoding with BGE models
8. **Chunk metadata completeness** — every chunk must carry: doc_name, circular_id, category, page_number, date, source_url, citation
9. **Async routes** — all FastAPI route functions must be `async def`
10. **Python 3.11+** — use modern syntax: `list[dict]` not `List[Dict]`, `X | None` not `Optional[X]`
```