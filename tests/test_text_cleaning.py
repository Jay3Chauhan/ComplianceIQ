"""Unit tests for PDF text cleanup and section detection."""

from ingestion.text_cleaning import (
    Line,
    SectionTracker,
    classify_heading,
    clean_page,
    find_boilerplate,
    is_low_value,
    is_toc_page,
    strip_footnote_markers,
)


def _lines(*texts: str, bold: bool = False) -> list[Line]:
    return [Line(t, bold) for t in texts]


def test_strip_footnote_markers() -> None:
    assert strip_footnote_markers("Direct Plan62") == "Direct Plan"
    assert strip_footnote_markers("64. 156Wire Transfer") == "64. Wire Transfer"
    assert strip_footnote_markers("Rules, 1957") == "Rules, 1957"


def test_find_boilerplate_detects_running_footer() -> None:
    pages = [
        _lines(f"Body text on page {i} about mutual funds.", "More content here.", f"{i}",
               "Master Circular for Mutual Funds as on March 31, 2024")
        for i in range(1, 9)
    ]
    patterns = find_boilerplate(pages)
    assert "master circular for mutual funds as on march #, #" in patterns


def test_clean_page_reflows_and_dehyphenates() -> None:
    tracker = SectionTracker()
    blocks = clean_page(
        _lines("The regulated entity shall ensure that the cus-", "tomer is identified before", "onboarding.",
               "(a) first item", "(b) second item"),
        set(), tracker, doc_has_bold=False,
    )
    texts = [b["text"] for b in blocks]
    assert texts[0] == "The regulated entity shall ensure that the customer is identified before onboarding."
    assert texts[1:] == ["(a) first item", "(b) second item"]


def test_clean_page_drops_page_numbers_and_boilerplate() -> None:
    blocks = clean_page(_lines("12", "Running Header Text", "Real content line here."),
                        {"running header text"}, SectionTracker(), doc_has_bold=False)
    assert [b["text"] for b in blocks] == ["Real content line here."]


def test_bold_headings_set_section() -> None:
    tracker = SectionTracker()
    page = [Line("CHAPTER VI", True), Line("Customer Due Diligence", True),
            Line("38. Periodic Updation", True), Line("Periodic updation shall be carried out.")]
    blocks = clean_page(page, set(), tracker, doc_has_bold=True)
    assert blocks[-1]["section"] == "CHAPTER VI Customer Due Diligence › 38. Periodic Updation"


def test_chapter_title_on_next_line_is_attached() -> None:
    tracker = SectionTracker()
    clean_page(_lines("CHAPTER II", "General", "4. (a) There shall be a KYC policy."), set(), tracker,
               doc_has_bold=False)
    assert tracker.chapter == "CHAPTER II – General"


def test_annexure_only_counts_at_page_top() -> None:
    assert classify_heading("Annexure-34 – Application to SEBI", False, True, True) is not None
    assert classify_heading("Annexure-34 – Application to SEBI", False, False, True) is None


def test_bold_sentence_fragment_is_not_heading() -> None:
    assert classify_heading("shall be maintained by the RE,", True, False, True) is None


def test_toc_page_detection() -> None:
    toc = _lines("Table of Contents", *[f"Chapter {i} Some Title ......... {i * 3}" for i in range(1, 12)])
    assert is_toc_page(toc, set(), in_front_matter=True)
    table = _lines("Instalment", "Outstanding", *[str(n) for n in range(20)])
    assert not is_toc_page(table, set(), in_front_matter=True)


def test_is_low_value() -> None:
    assert is_low_value("short")
    assert is_low_value("1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26")
    assert not is_low_value("Periodic updation shall be carried out at least once every two years for high risk.")
