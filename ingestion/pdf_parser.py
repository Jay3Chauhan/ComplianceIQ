"""
PDF text extraction (PyMuPDF with font info, pdfplumber fallback) and cleanup
into section-aware paragraph blocks per page.
"""

from pathlib import Path

import pymupdf
from loguru import logger

from ingestion.text_cleaning import (
    Line,
    SectionTracker,
    clean_page,
    find_boilerplate,
    is_toc_page,
)

BOLD_FLAG = 16


def _span_is_bold(span: dict) -> bool:
    return bool(span["flags"] & BOLD_FLAG) or "bold" in span["font"].lower()


def _line_text(spans: list[dict]) -> str:
    """Joins spans, inserting a space where the PDF positioned words apart."""
    text = ""
    prev_x1: float | None = None
    for span in spans:
        x0 = span["bbox"][0]
        if prev_x1 is not None and x0 - prev_x1 > span["size"] * 0.15 and not text.endswith(" "):
            text += " "
        text += span["text"]
        prev_x1 = span["bbox"][2]
    return text


def extract_lines(pdf_path: str) -> list[list[Line]]:
    """One list of lines per page (empty pages kept as [])."""
    try:
        pages: list[list[Line]] = []
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                lines: list[Line] = []
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        spans = [s for s in line["spans"] if s["text"].strip()]
                        if not spans:
                            continue
                        lines.append(Line(_line_text(spans), all(_span_is_bold(s) for s in spans)))
                pages.append(lines)
        return pages
    except Exception as e:
        logger.error(f"PyMuPDF extraction failed for {pdf_path}: {e}")
        return _extract_with_pdfplumber(pdf_path)


def _extract_with_pdfplumber(pdf_path: str) -> list[list[Line]]:
    try:
        import pdfplumber
    except ImportError as e:
        logger.error(f"pdfplumber unavailable for fallback extraction: {e}")
        return []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return [
                [Line(l) for l in (page.extract_text() or "").split("\n") if l.strip()]
                for page in pdf.pages
            ]
    except Exception as e:
        logger.error(f"pdfplumber extraction also failed for {pdf_path}: {e}")
        return []


def parse_pdf(pdf_path: str, doc_metadata: dict) -> list[dict]:
    """
    Parses a PDF into cleaned pages.

    Returns one dict per non-empty page:
      page_number, total_pages, text, blocks=[{text, section}], + document metadata
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    raw_pages = extract_lines(pdf_path)
    boilerplate = find_boilerplate(raw_pages)
    doc_has_bold = sum(l.bold for p in raw_pages for l in p) >= 5
    tracker = SectionTracker()
    total = len(raw_pages)
    filename = doc_metadata.get("filename") or Path(pdf_path).name

    pages: list[dict] = []
    toc_pages = 0
    front_matter = max(10, int(total * 0.15))
    for idx, lines in enumerate(raw_pages):
        if is_toc_page(lines, boilerplate, in_front_matter=idx < front_matter):
            toc_pages += 1
            continue
        blocks = clean_page(lines, boilerplate, tracker, doc_has_bold)
        if not blocks:
            continue
        pages.append({
            "page_number": idx + 1,
            "total_pages": total,
            "text": "\n".join(b["text"] for b in blocks),
            "blocks": blocks,
            "doc_id": doc_metadata.get("doc_id") or Path(filename).stem,
            "doc_name": doc_metadata["name"],
            "circular_id": doc_metadata.get("circular_id", ""),
            "category": doc_metadata.get("category", "GENERAL"),
            "subcategory": doc_metadata.get("subcategory", ""),
            "date": doc_metadata.get("date", ""),
            "issuer": doc_metadata.get("issuer", ""),
            "filename": filename,
            "source_url": doc_metadata.get("url", ""),
        })

    logger.info(
        f"Parsed {len(pages)}/{total} pages from {Path(pdf_path).name} "
        f"({len(boilerplate)} boilerplate patterns, {toc_pages} contents pages skipped)"
    )
    return pages
