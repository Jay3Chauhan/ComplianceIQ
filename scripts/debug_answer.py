"""Runs one question through the RAG pipeline and prints the raw answer and verification.

Usage: python -m scripts.debug_answer "question" [--mode regulatory]
"""

import argparse
import json

from rag.pipeline import RAGRequest, answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--mode", default="regulatory", choices=["auto", "regulatory", "general"])
    args = parser.parse_args()

    res = answer(RAGRequest(question=args.question, answer_mode=args.mode))
    print("MODE:", res.mode, "| CONFIDENCE:", res.confidence, "| REVISED:", res.revised, "| MODEL:", res.model)
    print("SOURCES:", [f"{s['doc_name'][:40]} p{s['page_number']} {s['relevance_score']}" for s in res.sources])
    print("-" * 80)
    print(res.answer)
    print("-" * 80)
    print(json.dumps(res.verification, indent=2))


if __name__ == "__main__":
    main()
