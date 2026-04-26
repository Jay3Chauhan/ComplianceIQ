"""
PDF text extraction using PyMuPDF.
Preserves page structure and extracts metadata per page.
"""

import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from loguru import logger


def extract_with_pymupdf(pdf_path: str) -> list[dict]:
    """
    Primary extraction using PyMuPDF.
    Returns list of page dicts with text and page number.
    """
    pages: list[dict] = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            text = "\n".join(
                line.strip() for line in text.split("\n") if line.strip()
            )
            if text:
                pages.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "total_pages": len(doc),
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
    pages: list[dict] = []
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
                        "total_pages": len(pdf.pages),
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

    enriched_pages: list[dict] = []
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
