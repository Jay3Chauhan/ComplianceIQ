"""
ComplianceIQ evaluation harness.

Retrieval eval (no LLM cost):
    python -m evaluation.run_eval retrieval --strategies legacy hybrid_rerank
Generation eval (uses Groq tokens — keep --limit small on the free tier):
    python -m evaluation.run_eval generation --limit 8 --negatives 4

Metrics
-------
Retrieval (per positive question, top_k chunks, scope=ALL by default):
  doc_hit@1 / doc_hit@k   expected source document appears at rank 1 / within top k
  mrr                     reciprocal rank of the first chunk from the expected document
  topic_recall@k          share of expected key terms present in the retrieved text
  success                 doc_hit@k AND topic_recall@k >= 0.5
Gate (positives vs out-of-corpus negatives):
  gate_accuracy           positives grounded + negatives rejected, at the configured threshold
  best_threshold          threshold on the gate score that maximises accuracy (for calibration)
Generation:
  topic_coverage          share of expected key terms present in the answer
  verified_rate           answers whose claims passed verification
  citation_valid_rate     answers whose citations all point to real sources
  refusal_accuracy        negatives correctly answered as not_found (regulatory mode)
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

DATASET_PATH = Path(__file__).parent / "test_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"


def load_dataset() -> tuple[list[dict], list[dict]]:
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return data["positives"], data["negatives"]


@dataclass
class StrategyOutput:
    chunks: list[dict]
    gate_score: float
    grounded: bool
    latency_ms: float
    extra: dict = field(default_factory=dict)


# ── Strategies ───────────────────────────────────────────────────────────────

def _legacy(query: str, category: str | None, top_k: int) -> StrategyOutput:
    """Previous production pipeline: v1 chunks, dense-only search + rerank, dense-score gate."""
    from evaluation import legacy_index
    from retrieval.reranker import rerank_chunks

    t0 = time.perf_counter()
    chunks = legacy_index.search(query, limit=top_k * 4, category=category)
    dense_top = chunks[0]["dense_score"] if chunks else 0.0
    chunks = rerank_chunks(query, chunks, top_k=top_k)
    latency = (time.perf_counter() - t0) * 1000
    return StrategyOutput(chunks, dense_top, dense_top >= 0.58, latency)


def _v2(strategy: str, rerank: bool):
    def run(query: str, category: str | None, top_k: int) -> StrategyOutput:
        from retrieval.retriever import retrieve

        t0 = time.perf_counter()
        result = retrieve(
            query,
            top_k=top_k,
            category=category,
            strategy=strategy,
            rerank=rerank,
            use_cache=False,
            apply_gate=False,
        )
        latency = (time.perf_counter() - t0) * 1000
        return StrategyOutput(
            result.chunks,
            result.gate_score,
            result.is_grounded,
            latency,
            {"timings": result.timings},
        )

    return run


STRATEGIES = {
    "legacy": _legacy,
    "dense": _v2("dense", rerank=False),
    "sparse": _v2("sparse", rerank=False),
    "hybrid": _v2("hybrid", rerank=False),
    "dense_rerank": _v2("dense", rerank=True),
    "hybrid_rerank": _v2("hybrid", rerank=True),
}


# ── Retrieval metrics ────────────────────────────────────────────────────────

def _topic_recall(text: str, topics: list[str]) -> float:
    if not topics:
        return 1.0
    low = text.lower()
    return sum(1 for t in topics if t.lower() in low) / len(topics)


def score_positive(q: dict, out: StrategyOutput, top_k: int) -> dict:
    files = [c.get("filename", "") for c in out.chunks[:top_k]]
    expected = q["expected_doc"].lower()
    ranks = [i for i, f in enumerate(files, 1) if expected in f.lower()]
    text = "\n".join(c.get("chunk_text", "") for c in out.chunks[:top_k])
    recall = _topic_recall(text, q.get("expected_topics", []))
    doc_hit_k = bool(ranks)
    return {
        "question": q["question"],
        "doc_hit@1": bool(ranks and ranks[0] == 1),
        "doc_hit@k": doc_hit_k,
        "mrr": 1 / ranks[0] if ranks else 0.0,
        "topic_recall@k": round(recall, 3),
        "success": doc_hit_k and recall >= 0.5,
        "gate_score": round(out.gate_score, 4),
        "grounded": out.grounded,
        "latency_ms": round(out.latency_ms),
        "top_sources": [
            f"{c.get('filename', '')} p.{c.get('page_number')}" for c in out.chunks[:3]
        ],
    }


def best_threshold(pos_scores: list[float], neg_scores: list[float]) -> tuple[float, float]:
    candidates = sorted(set(pos_scores + neg_scores))
    best = (0.0, 0.0)
    total = len(pos_scores) + len(neg_scores)
    for t in candidates:
        correct = sum(s >= t for s in pos_scores) + sum(s < t for s in neg_scores)
        acc = correct / total
        if acc > best[1]:
            best = (t, acc)
    return best


def run_retrieval_eval(strategies: list[str], top_k: int, use_category: bool) -> dict:
    positives, negatives = load_dataset()
    report: dict = {"top_k": top_k, "use_category": use_category, "strategies": {}}

    for name in strategies:
        fn = STRATEGIES[name]
        logger.info(f"── Strategy: {name}")
        rows = []
        for q in positives:
            cat = q.get("category") if use_category else None
            rows.append(score_positive(q, fn(q["question"], cat, top_k), top_k))
        neg_rows = []
        for q in negatives:
            out = fn(q["question"], None, top_k)
            neg_rows.append({
                "question": q["question"],
                "gate_score": round(out.gate_score, 4),
                "grounded": out.grounded,
                "top_source": out.chunks[0].get("filename") if out.chunks else None,
            })

        pos_scores = [r["gate_score"] for r in rows]
        neg_scores = [r["gate_score"] for r in neg_rows]
        thr, thr_acc = best_threshold(pos_scores, neg_scores)
        gate_correct = sum(r["grounded"] for r in rows) + sum(not r["grounded"] for r in neg_rows)

        n = len(rows)
        summary = {
            "success_rate": round(sum(r["success"] for r in rows) / n, 3),
            "doc_hit@1": round(sum(r["doc_hit@1"] for r in rows) / n, 3),
            "doc_hit@k": round(sum(r["doc_hit@k"] for r in rows) / n, 3),
            "mrr": round(statistics.mean(r["mrr"] for r in rows), 3),
            "topic_recall@k": round(statistics.mean(r["topic_recall@k"] for r in rows), 3),
            "gate_accuracy": round(gate_correct / (n + len(neg_rows)), 3),
            "best_threshold": round(thr, 4),
            "best_threshold_accuracy": round(thr_acc, 3),
            "pos_gate_score_min": round(min(pos_scores), 4),
            "neg_gate_score_max": round(max(neg_scores), 4),
            "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows)),
        }
        logger.success(f"{name}: {summary}")
        report["strategies"][name] = {"summary": summary, "positives": rows, "negatives": neg_rows}

    return report


# ── Generation eval ──────────────────────────────────────────────────────────

def run_generation_eval(limit: int, negatives_limit: int, pause: float = 20.0) -> dict:
    from rag.pipeline import RAGRequest, answer

    positives, negatives = load_dataset()
    rows = []
    for q in positives[:limit]:
        res = answer(RAGRequest(question=q["question"], answer_mode="regulatory"))
        ver = res.verification or {}
        rows.append({
            "question": q["question"],
            "mode": res.mode,
            "topic_coverage": round(_topic_recall(res.answer, q.get("expected_topics", [])), 3),
            "verification_status": ver.get("status"),
            "verification_score": ver.get("score"),
            "verification_method": ver.get("method"),
            "citations_valid": not ver.get("citation_issues"),
            "revised": res.revised,
            "confidence": res.confidence,
            "model": res.model,
            "latency_ms": res.latency_ms,
            "answer": res.answer,
        })
        time.sleep(pause)  # free tier: 8K tokens/min per model

    neg_rows = []
    for q in negatives[:negatives_limit]:
        res = answer(RAGRequest(question=q["question"], answer_mode="regulatory"))
        neg_rows.append({"question": q["question"], "mode": res.mode, "refused": res.mode == "not_found"})

    reg = [r for r in rows if r["mode"] == "regulatory"]
    summary = {
        "answered_from_documents": f"{len(reg)}/{len(rows)}",
        "topic_coverage": round(statistics.mean(r["topic_coverage"] for r in rows), 3) if rows else 0,
        "verified_rate": round(sum(r["verification_status"] == "verified" for r in reg) / len(reg), 3) if reg else 0,
        "verified_or_partial_rate": round(
            sum(r["verification_status"] in ("verified", "partially_verified") for r in reg) / len(reg), 3
        ) if reg else 0,
        "avg_verification_score": round(statistics.mean(r["verification_score"] or 0 for r in reg), 3) if reg else 0,
        "citation_valid_rate": round(sum(r["citations_valid"] for r in reg) / len(reg), 3) if reg else 0,
        "revised_count": sum(r["revised"] for r in reg),
        "refusal_accuracy": round(sum(r["refused"] for r in neg_rows) / len(neg_rows), 3) if neg_rows else None,
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows)) if rows else 0,
    }
    logger.success(f"generation: {summary}")
    return {"summary": summary, "positives": rows, "negatives": neg_rows}


def _save(name: str, report: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Saved report → {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="ComplianceIQ evaluation")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("retrieval")
    r.add_argument("--strategies", nargs="+", default=["hybrid_rerank"], choices=list(STRATEGIES))
    r.add_argument("--top-k", type=int, default=6)
    r.add_argument("--use-category", action="store_true", help="Apply each question's category filter")

    g = sub.add_parser("generation")
    g.add_argument("--limit", type=int, default=8)
    g.add_argument("--negatives", type=int, default=4)
    g.add_argument("--pause", type=float, default=20.0, help="Seconds between questions (rate limits)")

    args = parser.parse_args()
    if args.cmd == "retrieval":
        _save("retrieval", run_retrieval_eval(args.strategies, args.top_k, args.use_category))
    else:
        _save("generation", run_generation_eval(args.limit, args.negatives, args.pause))


if __name__ == "__main__":
    main()
