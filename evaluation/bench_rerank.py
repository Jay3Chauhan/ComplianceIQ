"""Micro-benchmark of candidate cross-encoders (latency + score separation)."""

import sys
import time

from evaluation import legacy_index

QUERIES = [
    "What is the Key Fact Statement for digital loans?",
    "What is the EPF interest rate declared by EPFO this year?",
    "What are the penalties for non-compliance with KYC norms?",
    "Explain Python list comprehensions with an example",
]


def main() -> None:
    from sentence_transformers import CrossEncoder

    models = sys.argv[1:] or ["BAAI/bge-reranker-base", "cross-encoder/ms-marco-MiniLM-L-6-v2"]
    for name in models:
        ce = CrossEncoder(name, max_length=384)
        for q in QUERIES:
            docs = [c["chunk_text"] for c in legacy_index.search(q, 20)]
            t0 = time.perf_counter()
            s = ce.predict([(q, d) for d in docs], batch_size=16, show_progress_bar=False)
            print(f"{name[-22:]:22} {q[:40]:40} {1000*(time.perf_counter()-t0):6.0f}ms max={max(s):.3f}")


if __name__ == "__main__":
    main()
