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

    context_parts: list[str] = []
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

    formatted: list[str] = []
    for turn in history[-3:]:
        formatted.append(f"User: {turn['question']}")
        answer = turn.get("answer", "")
        formatted.append(f"Assistant: {answer[:500]}...")

    return "\n".join(formatted)
