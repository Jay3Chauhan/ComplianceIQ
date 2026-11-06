"""Curated starter questions per regulator (each verified to be answerable from the corpus)."""

SUGGESTIONS: dict[str, list[str]] = {
    "RBI": [
        "What are the periodic KYC update timelines for different risk categories?",
        "What must a Key Fact Statement contain for digital loans?",
        "Can a digital lending app access the borrower's contact list?",
        "What is Video-based Customer Identification Process (V-CIP)?",
    ],
    "SEBI": [
        "What is swing pricing for mutual fund schemes?",
        "What are the total expense ratio limits for mutual fund schemes?",
        "How should stock brokers settle running accounts of clients?",
        "What are the norms for margin trading facility offered by stock brokers?",
    ],
    "AA": [
        "What is the minimum net owned fund required for an NBFC-AA?",
        "What details must a consent artefact contain?",
        "What is the role of a Financial Information Provider?",
        "Can an Account Aggregator store customer financial information?",
    ],
}


def starter_questions(category: str = "ALL", limit: int = 4) -> list[str]:
    """Interleaves regulators for ALL so every category is represented."""
    if category in SUGGESTIONS:
        pool = SUGGESTIONS[category]
    else:
        pool = [q for group in zip(*SUGGESTIONS.values()) for q in group]
    return pool[:limit]
