"""
RAGAS evaluation pipeline for ComplianceIQ.
Runs the test questions through the RAG stack and scores it on faithfulness,
answer relevancy, and context precision.

Usage: python -m evaluation.ragas_eval
"""

import json
from pathlib import Path
from loguru import logger

from retrieval.retriever import retrieve_chunks
from llm.groq_client import generate_answer

TEST_QUESTIONS_PATH = Path(__file__).parent / "test_questions.json"


def run_pipeline() -> list[dict]:
    """Runs each test question through retrieval + generation and collects results."""
    with open(TEST_QUESTIONS_PATH) as f:
        questions = json.load(f)

    records: list[dict] = []
    for i, q in enumerate(questions, 1):
        logger.info(f"[{i}/{len(questions)}] {q['question']}")
        try:
            chunks = retrieve_chunks(
                query=q["question"],
                top_k=5,
                category_filter=q.get("category"),
            )
            if not chunks:
                records.append({
                    "question": q["question"],
                    "answer": "",
                    "contexts": [],
                    "expected_topics": q.get("expected_topics", []),
                })
                continue

            result = generate_answer(question=q["question"], chunks=chunks)
            records.append({
                "question": q["question"],
                "answer": result["answer"],
                "contexts": [c["chunk_text"] for c in chunks],
                "expected_topics": q.get("expected_topics", []),
            })
        except Exception as e:
            logger.error(f"Failed on question: {q['question']} | {e}")
            records.append({
                "question": q["question"],
                "answer": f"ERROR: {e}",
                "contexts": [],
                "expected_topics": q.get("expected_topics", []),
            })

    return records


def evaluate_with_ragas(records: list[dict]) -> dict:
    """
    Scores the records using RAGAS metrics.
    Falls back to a simple keyword-overlap score if RAGAS/LLM setup is missing.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_precision

        dataset = Dataset.from_list([
            {
                "question": r["question"],
                "answer": r["answer"],
                "contexts": r["contexts"],
            }
            for r in records
            if r["answer"] and not r["answer"].startswith("ERROR")
        ])

        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy, context_precision],
        )
        return dict(result)

    except Exception as e:
        logger.warning(f"RAGAS evaluation unavailable, using keyword fallback: {e}")
        return keyword_overlap_score(records)


def keyword_overlap_score(records: list[dict]) -> dict:
    """Cheap fallback: fraction of expected_topics present in the answer."""
    scores: list[float] = []
    for r in records:
        if not r["answer"] or r["answer"].startswith("ERROR"):
            continue
        topics = r.get("expected_topics", [])
        if not topics:
            continue
        answer_lower = r["answer"].lower()
        hits = sum(1 for t in topics if t.lower() in answer_lower)
        scores.append(hits / len(topics))

    avg = sum(scores) / len(scores) if scores else 0.0
    return {"keyword_overlap": avg, "evaluated_count": len(scores)}


def main() -> None:
    logger.info("Running RAGAS evaluation pipeline...")
    records = run_pipeline()

    out_path = Path(__file__).parent / "eval_results.json"
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    logger.info(f"Saved raw records to {out_path}")

    scores = evaluate_with_ragas(records)
    logger.success(f"Evaluation scores: {scores}")


if __name__ == "__main__":
    main()
