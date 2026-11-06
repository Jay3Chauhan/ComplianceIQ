"""
Cleans raw PDF lines into structured paragraphs with section labels.

- Removes running headers/footers, page numbers and table-of-contents pages
- Re-flows hard-wrapped lines into paragraphs and fixes hyphenated breaks
- Detects headings (bold font first, text patterns as fallback) and tracks the
  current chapter / heading so every paragraph knows its section
"""

import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class Line:
    text: str
    bold: bool = False


LIGATURES = {
    "\ufb01": "fi", "\ufb02": "fl", "\ufb00": "ff", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u00a0": " ", "\u200b": "", "\u00ad": "",
}

PAGE_NUMBER_RE = re.compile(r"^(page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?(\s*(of|/)\s*\d{1,4})?$", re.I)
TOC_RE = re.compile(r"(\.\s?){6,}\s*\d+\s*$")

CHAPTER_RE = re.compile(r"^(chapter|part)\s*[-–—]?\s*([ivxlc]+|\d+)\b[\s.:–—-]*(.*)$", re.I)
ANNEX_RE = re.compile(r"^(annex(ure)?|appendix|schedule)\b[\s\w.:–—-]{0,80}$", re.I)
# "16. Customer Due Diligence" or "2.5 Direct Plan"; a bare "82 Regulation…" is a footnote
NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}\.|\d{1,2}\.\d{1,2}\.?)\s+([A-Z(].{2,90})$")

BLOCK_START_RE = re.compile(
    r"^("
    r"\(?[a-z]{1,2}\)\s"                   # a) (a) aa)
    r"|\(?[ivxlc]{1,6}[.)]\s"              # i. (iv) xii)
    r"|\(?\d{1,3}(\.\d{1,3}){0,3}[.)]?\s"  # 1. 2.5 2.5.1 (3)
    r"|[a-zA-Z]\.\s"                       # a. B.
    r"|[•▪●◦■\-–]\s"                       # bullets
    r"|(chapter|part|section|annex|annexure|appendix|schedule)\b"
    r"|explanation\b|provided\b|note\b|illustration\b"
    r")",
    re.I,
)

CLAUSE_VERBS_RE = re.compile(
    r"\b(shall|should|must|may|means|is|are|was|were|has|have|will|can|include|includes)\b", re.I
)
TRAILING_CONNECTOR_RE = re.compile(r"\b(and|or|of|the|to|for|in|with|by|a|an|as)$", re.I)
STOPWORDS = {"of", "the", "and", "for", "in", "on", "to", "a", "an", "by", "with", "or", "under", "at", "as"}

# A bold line starting like this begins a new heading rather than continuing one
NEW_HEADING_RE = re.compile(r"^(\d{1,2}(\.\d{1,2}){0,2}\.?\s+\S|[A-Z]\.\s+\S)")

MAX_HEADING_CHARS = 200
MAX_HEADING_LINES = 3


def normalize_line(line: str) -> str:
    for src, dst in LIGATURES.items():
        line = line.replace(src, dst)
    return re.sub(r"\s+", " ", line).strip()


def strip_footnote_markers(text: str) -> str:
    """'Direct Plan62' → 'Direct Plan', '64. 156Wire Transfer' → '64. Wire Transfer'."""
    text = re.sub(r"(?<=[A-Za-z\)’'\"”])\d{1,3}:?$", "", text)
    text = re.sub(r"^(\d{1,3}(?:\.\d{1,3})*\.?)\s*\d{1,3}(?=[A-Z“\"])", r"\1 ", text)
    return text.strip()


def _boilerplate_key(line: str) -> str:
    return re.sub(r"\d+", "#", line.lower())


def find_boilerplate(pages: list[list[Line]], edge: int = 4) -> set[str]:
    """Lines repeated at the top/bottom of many pages (running headers/footers)."""
    if len(pages) < 4:
        return set()
    counts: Counter[str] = Counter()
    for raw in pages:
        lines = [t for t in (normalize_line(l.text) for l in raw) if t]
        edges = {_boilerplate_key(l) for l in lines[:edge] + lines[-edge:] if 3 <= len(l) <= 150}
        counts.update(edges)
    min_pages = max(3, int(len(pages) * 0.3))
    return {k for k, c in counts.items() if c >= min_pages}


def is_toc_page(lines: list[Line], boilerplate: set[str], in_front_matter: bool) -> bool:
    """Index / table-of-contents pages: mostly heading-like entries."""
    norm = [t for t in (normalize_line(l.text) for l in lines) if t and _boilerplate_key(t) not in boilerplate]
    if len(norm) < 8:
        return False
    if any(re.fullmatch(r"(table of )?contents|index", l.strip(" :").lower()) for l in norm[:5]):
        return True
    if not in_front_matter:
        return False
    text_entries = sum(
        1 for l in norm
        if TOC_RE.search(l)
        or CHAPTER_RE.match(l)
        or ANNEX_RE.match(l)
        or re.search(r"[A-Za-z]{3,}.*\s\d{1,4}$", l)
        or re.match(r"^\d{1,3}\.\s+(annex|chapter|appendix|schedule|part)", l, re.I)
    )
    page_numbers = sum(1 for l in norm if PAGE_NUMBER_RE.match(l))
    # Numeric tables are mostly bare numbers; real contents pages are mostly titled entries
    return text_entries / len(norm) >= 0.3 and (text_entries + page_numbers) / len(norm) >= 0.5


def _is_title_like(text: str) -> bool:
    text = strip_footnote_markers(text)
    words = text.split()
    if not words or len(words) > 12 or len(text) > 90:
        return False
    if text[-1] in ".,;-–" or CLAUSE_VERBS_RE.search(text) or TRAILING_CONNECTOR_RE.search(text):
        return False
    content = [w for w in words if w.lower() not in STOPWORDS]
    if not content:
        return False
    capitalised = sum(1 for w in content if w[0].isupper() or w[0] in "(“\"'")
    return capitalised / len(content) >= 0.6


def _is_caps_heading(line: str) -> bool:
    words = re.findall(r"[A-Za-z]{2,}", line)
    letters = sum(ch.isalpha() or ch == " " for ch in line)
    return (
        line.isupper()
        and 8 <= len(line) <= 80
        and len(words) >= 2
        and letters / len(line) >= 0.8
        and not line.startswith("(")
        and not CLAUSE_VERBS_RE.search(line)
    )


def classify_heading(text: str, bold: bool, first_on_page: bool, doc_has_bold: bool) -> tuple[str, str] | None:
    """
    Returns ("chapter" | "heading", label) for structural headings, else None.
    Annexure headings only count as the first line of a page so index listings
    do not hijack the section of everything that follows.
    """
    text = strip_footnote_markers(text)
    if not re.search(r"[A-Za-z]{3,}", text):
        return None
    label = text.rstrip(" .:-–—")

    m = CHAPTER_RE.match(text)
    if m and len(text) <= 150 and (bold or first_on_page or not m.group(3) or _is_title_like(m.group(3))):
        return "chapter", label
    if ANNEX_RE.match(text) and first_on_page:
        return "chapter", label

    if bold:
        if len(text) <= MAX_HEADING_CHARS and text[-1] not in ",;" and not text[:1].islower():
            return "heading", label
        return None

    if doc_has_bold:
        return None
    m = NUMBERED_HEADING_RE.match(text)
    if m and _is_title_like(m.group(2)):
        return "heading", label
    if _is_caps_heading(text):
        return "heading", text.title()
    return None


class SectionTracker:
    """Keeps the current chapter and heading across pages."""

    def __init__(self) -> None:
        self.chapter = ""
        self.heading = ""
        self._chapter_needs_title = False

    @property
    def needs_chapter_title(self) -> bool:
        return self._chapter_needs_title

    def update(self, kind: str, label: str) -> None:
        if kind == "chapter":
            m = CHAPTER_RE.match(label)
            self.chapter = label
            self.heading = ""
            self._chapter_needs_title = bool(m) and not m.group(3)
        elif self._chapter_needs_title:
            self.chapter = f"{self.chapter} – {label}"
            self._chapter_needs_title = False
        else:
            self.heading = label

    @property
    def label(self) -> str:
        return " › ".join(p for p in (self.chapter, self.heading) if p)[:200]


def _join(prev: str, line: str) -> str:
    if prev.endswith("-") and line[:1].islower():
        return prev[:-1] + line
    return f"{prev} {line}"


def _group_lines(lines: list[Line], boilerplate: set[str]) -> list[Line]:
    """Normalises lines, drops noise, and merges consecutive bold lines (wrapped headings)."""
    out: list[Line] = []
    for raw in lines:
        text = normalize_line(raw.text)
        if not text or PAGE_NUMBER_RE.match(text) or _boilerplate_key(text) in boilerplate:
            continue
        if TOC_RE.search(text):
            continue
        if raw.bold:
            text = strip_footnote_markers(text)
        prev = out[-1] if out else None
        if (
            raw.bold and prev is not None and prev.bold
            and len(prev.text) + len(text) <= MAX_HEADING_CHARS
            and prev.text.count("\n") < MAX_HEADING_LINES - 1
            and not CHAPTER_RE.match(text)
            and not ANNEX_RE.match(text)
            and not NEW_HEADING_RE.match(text)
        ):
            prev.text = f"{prev.text}\n{text}"
            continue
        out.append(Line(text, raw.bold))
    for line in out:
        line.text = line.text.replace("\n", " ")
    return out


def clean_page(
    lines: list[Line],
    boilerplate: set[str],
    tracker: SectionTracker,
    doc_has_bold: bool,
) -> list[dict]:
    """
    Converts one page of raw lines into paragraph blocks:
    [{"text": str, "section": str, "is_heading"?: bool}, ...]
    """
    blocks: list[dict] = []
    current = ""
    current_section = tracker.label

    def flush() -> None:
        nonlocal current
        if current.strip():
            blocks.append({"text": current.strip(), "section": current_section})
        current = ""

    for idx, line in enumerate(_group_lines(lines, boilerplate)):
        text = line.text
        heading = classify_heading(text, line.bold, idx == 0, doc_has_bold)
        if heading is None and tracker.needs_chapter_title and _is_title_like(text):
            heading = ("heading", text)
        if heading:
            flush()
            tracker.update(*heading)
            current_section = tracker.label
            blocks.append({"text": strip_footnote_markers(text), "section": current_section, "is_heading": True})
            continue

        if not current:
            current = text
            current_section = tracker.label
        elif BLOCK_START_RE.match(text):
            flush()
            current = text
            current_section = tracker.label
        else:
            current = _join(current, text)
    flush()
    return blocks


def is_low_value(text: str) -> bool:
    """Table-of-contents fragments and near-empty text add noise to retrieval."""
    if len(text) < 60:
        return True
    letters = sum(ch.isalpha() for ch in text)
    if letters / max(len(text), 1) < 0.45:
        return True
    return len(re.findall(r"\.{4,}|(?:\.\s){4,}", text)) >= 3
