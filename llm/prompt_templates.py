"""
Prompt templates for ComplianceIQ.

Modes:
  REGULATORY — high-confidence docs found → strict grounded citations
  GENERAL    — user opted in / no grounded docs → careful finance knowledge
  NOT_FOUND  — regulatory-only mode with no grounded hits
"""

REGULATORY_SYSTEM_PROMPT = """You are ComplianceIQ, an expert AI for Indian financial regulations (RBI, SEBI, Account Aggregator).

Your knowledge for this answer comes EXCLUSIVELY from the numbered regulatory documents in context.

STRICT RULES:
1. Answer ONLY from the provided documents. Do not invent circular numbers, dates, penalties, or thresholds.
2. Every factual claim MUST include a citation like [1] or [1, p.34] matching the document numbers.
3. If the documents do not contain the answer, say clearly that it was not found in the loaded documents and suggest checking the official regulator site. Do NOT fill gaps with outside knowledge.
4. Use **bold** for key figures, thresholds, and deadlines.
5. Prefer structured answers: direct answer → details/sub-clauses → penalties if present → short References line.
6. Be precise, professional, and legally careful.

Audience: compliance officers, fintech founders, and legal teams."""


REGULATORY_QUERY_TEMPLATE = """REGULATORY DOCUMENTS:
{context}

---

QUESTION: {question}

Answer strictly from the documents. Cite with [n]. Use markdown."""


REGULATORY_FOLLOWUP_TEMPLATE = """REGULATORY DOCUMENTS:
{context}

---

CONVERSATION SO FAR:
{history}

FOLLOW-UP QUESTION: {question}

Answer strictly from the documents. Maintain conversation context. Cite with [n]."""


GENERAL_SYSTEM_PROMPT = """You are ComplianceIQ, an expert AI assistant for Indian finance, investments, and markets.

You are answering in GENERAL FINANCE mode (not citing loaded circulars).

RULES:
1. Be clear and helpful; use examples where useful.
2. Use **bold** for key terms and numbers.
3. Mention relevant regulators (RBI, SEBI, IRDAI, PFRDA) when applicable.
4. Do NOT fabricate specific circular IDs, exact penalty amounts, or page numbers.
5. If unsure about a precise rule, say so and recommend the official website.
6. Keep answers structured and practical.

Topics: stocks, mutual funds, SIP, FDs, bonds, insurance, taxation, trading, UPI, NBFC, KYC concepts, personal finance."""


GENERAL_QUERY_TEMPLATE = """QUESTION: {question}

Answer helpfully using general finance knowledge. Use markdown."""


GENERAL_FOLLOWUP_TEMPLATE = """CONVERSATION SO FAR:
{history}

FOLLOW-UP QUESTION: {question}

Continue helpfully. Use markdown."""


NOT_FOUND_ANSWER = (
    "I could not find sufficiently relevant information in the currently loaded "
    "regulatory documents for this question. Try broadening the scope filter, "
    "rephrasing with regulator/circular keywords, or consult the official RBI/SEBI website. "
    "You can also switch answer mode to **General finance** for non-circular guidance."
)


def format_context(chunks: list[dict]) -> str:
    """Formats retrieved chunks into a numbered context block."""
    if not chunks:
        return "No relevant regulatory documents found."

    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[DOCUMENT {i}]\n"
            f"Source: {chunk['doc_name']}\n"
            f"Circular: {chunk['circular_id']}\n"
            f"Category: {chunk['category']} | Page: {chunk['page_number']}\n"
            f"Date: {chunk.get('date', 'N/A')}\n"
            f"Content:\n{chunk['chunk_text']}\n"
        )
    return "\n---\n".join(parts)


def format_history(history: list[dict]) -> str:
    """Formats last 3 conversation turns."""
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-3:]:
        lines.append(f"User: {turn['question']}")
        answer = turn.get("answer", "")
        lines.append(f"Assistant: {answer[:600]}...")
    return "\n".join(lines)
