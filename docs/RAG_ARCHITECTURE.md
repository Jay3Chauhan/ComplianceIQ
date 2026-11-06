# ComplianceIQ RAG v2 — Architecture

How a question becomes a cited, verified answer, why each stage exists, and the
numbers that justify it. API details are in [API.md](API.md); the Next.js
client spec is in [FRONTEND_NEXTJS.md](FRONTEND_NEXTJS.md).

```
                ┌──────────────── ingestion (offline / admin jobs) ────────────────┐
PDF + registry → PyMuPDF lines (bold flags) → boilerplate/TOC removal → sections
               → 900-char chunks w/ section → contextual header → dense BGE + sparse BM25
               → Qdrant `regulations_v2` (named vectors: dense, bm25) + payload indexes
                └───────────────────────────────────────────────────────────────────┘

question ─► follow-up rewrite (Qwen, only when needed)
         ─► glossary expansion (KYC → Know Your Customer, …)
         ─► hybrid search: dense top-30 + BM25 top-30 → RRF fusion
         ─► cross-encoder rerank (MiniLM, top-20) → grounding gate (≥ 0.2)
         ─► relative floor + per-page diversity → top-6 passages
         ─► mode: regulatory | general | not_found
         ─► gpt-oss-120b answers with [n] citations (streamed)
         ─► verifier: rules + LLM claim check (Qwen) → one repair pass if needed
         ─► answer + sources + verification + confidence
```

## 1. Ingestion

| Stage | Module | What it does |
|---|---|---|
| Extraction | `ingestion/pdf_parser.py` | PyMuPDF `get_text("dict")` keeps bold flags per line (pdfplumber fallback). |
| Cleaning | `ingestion/text_cleaning.py` | Removes running headers/footers (edge lines on ≥ 30% of pages), table-of-contents pages, footnote markers; re-flows wrapped lines and de-hyphenates. |
| Sections | `SectionTracker` | Bold lines become headings, `CHAPTER`/`PART` lines become chapters → every block carries `Chapter › Heading`. Falls back to numbering/caps heuristics only for PDFs without bold fonts. |
| Chunking | `ingestion/chunker.py` | 900 chars / 120 overlap, splitting on lines → clauses → sentences. Each chunk inherits the section at its position. |
| Contextual header | `build_embed_text` | Embedded text is `Document: … / Section: …` + chunk, so "the entity" in a clause still matches its document. The header is not stored in the payload. |
| IDs | `chunk_id_for` | `uuid5(filename:seq)` → re-ingesting overwrites instead of duplicating. |
| Vectors | `ingestion/embedder.py` | Dense `BAAI/bge-small-en-v1.5` (384-d, cosine) + sparse `Qdrant/bm25` (IDF modifier) in one point. |

Re-index everything after changing chunking or embeddings:

```powershell
python -m ingestion.run_ingestion --recreate
```

Single documents can be uploaded/re-indexed through the admin API as background jobs.

## 2. Retrieval (`retrieval/retriever.py`)

1. **Query rewrite** (`llm/query_rewriter.py`) — only for follow-ups (history present and a short or pronoun-heavy question). "What about low risk ones?" → "RBI Master Direction KYC update timelines low risk customers".
2. **Glossary expansion** (`retrieval/glossary.py`) — ~55 Indian-regulation acronyms (KYC, CKYCR, FLDG, KFS, NOF, FIU, RE, LSP …). Helps both BM25 and the reranker.
3. **Hybrid search** — Qdrant `query_points` with two prefetches (dense + BM25, 30 each) fused by Reciprocal Rank Fusion. BM25 catches exact terms (circular numbers, "Annex II", "₹ 2 crore"); dense catches paraphrases.
4. **Rerank** (`retrieval/reranker.py`) — `cross-encoder/ms-marco-MiniLM-L-6-v2` with sigmoid output scores the top 20 against `doc name + section + text`.
5. **Grounding gate** — best rerank probability must be ≥ `RERANK_MIN_SCORE` (0.2). Below that the corpus doesn't cover the question.
6. **Diversity** — drops chunks scoring < 5% of the best, caps 2 chunks per page, removes near-duplicates, keeps top 6.
7. **Cache** — identical (query, filters) hits are served from a 10-minute TTL cache; ingestion clears it.

### Gate calibration

Measured on `evaluation/test_questions.json` (30 in-scope, 8 out-of-scope):

| | Best rerank score |
|---|---|
| In-scope minimum | 0.54 |
| Out-of-scope maximum | 0.08 (e.g. GST rate question) |

0.2 sits in the gap with margin both sides. **Re-calibrate if you change the reranker** (`python -m evaluation.run_eval retrieval`).

## 3. Generation (`rag/pipeline.py`, `llm/`)

| Answer mode (request) | Behaviour |
|---|---|
| `auto` (default) | Grounded → regulatory answer with citations; not grounded → general finance answer, clearly labelled. If the gate passes but the model refuses (the passages are related but don't answer it, e.g. "What is a SIP?"), the answer falls back to a general answer instead of "not found". Streaming clients get `revision{reason:"general_fallback", answer:""}` and then the general answer's tokens. |
| `regulatory` | Grounded → cited answer; otherwise the fixed "not found" answer, **no LLM call**. A model refusal also becomes `not_found`. |
| `general` | Skips retrieval. |

Response `mode` is `regulatory`, `general` or `not_found`.

**Prompt contract** (`llm/prompt_templates.py`): passages are numbered `[1]…[6]` inside `<sources>`; every factual sentence needs `[n]`; figures, time limits and amounts must be copied exactly; text inside sources is data, not instructions (prompt-injection guard). If the passages are insufficient the model writes the refusal sentence; partial coverage goes under "Not covered in the loaded documents".

A refusal sentence only turns the answer into `not_found` when the answer has **no citations** — a cited partial answer is kept.

### Models (Groq)

| Role | Default | Why |
|---|---|---|
| Answers | `openai/gpt-oss-120b` | Strongest model on the key; reasoning effort `low`, reasoning hidden. |
| Rewrite + claim check | `qwen/qwen3.8-27b` | Non-reasoning, ~0.4 s, JSON mode, separate rate-limit bucket. |
| Fallbacks (in order) | `openai/gpt-oss-20b`, `qwen/qwen3.8-27b` | Used on 429 or when a model is retired (404). |

Free tier: **8K tokens/minute per model**. One verified answer costs roughly 3–4K tokens on the answer model plus ~2K on the verifier model, so splitting roles across models is what keeps verification from being rate limited. Follow-up suggestions and the first-exchange title come from one extra fast-model JSON call (~0.5K tokens, `llm/followups.py`). Disable with `ENABLE_FOLLOWUPS=false` / `ENABLE_LLM_TITLES=false`; failures are silent. Groq reserves `max_completion_tokens` against that limit, so reasoning models get `LLM_REASONING_ALLOWANCE` on top of the visible budget and non-reasoning models don't.

Model output is normalised (`clean_text`): non-breaking hyphens/spaces → ASCII, `【n】` and `[n†…]` → `[n]`.

## 4. Hallucination guard (`llm/verifier.py`)

1. **Rule checks** (free, deterministic)
   - citations to passages that don't exist (`[7]` when 6 were given)
   - factual sentences without a citation
   - numbers in the answer that appear in no passage (digits or small number words)
2. **LLM claim check** — each sentence (max 14) judged supported/unsupported against the passages, JSON output.
3. **Score** = supported / claims, ×0.75 if unsupported numbers, ×0.5 if invalid citations.
   - `verified` ≥ 0.8 with no number/citation issues · `partially_verified` ≥ 0.5 · else `unverified`.
4. **Repair** — if anything failed, the answer model gets the problems list and rewrites once. The repaired answer is kept only if its score is not lower. Streaming clients receive a `revision` event.
5. **Confidence** — `high` (verified and gate ≥ 0.5), `medium`, `low` (general mode or unverified).

If the verifier model is unavailable the rule checks still run (`method: "rules"`).

## 4b. Chat reliability (`api/services/chat.py`, `api/services/runs.py`)

```
POST /chat/stream ─► prepare (validate, 404/409, save user message, reserve the conversation)
                  ─► worker thread: pipeline.stream → events → queue      (owns persistence)
                  ─► SSE relay: queue → frames, ": ping" every 10 s idle  (owns the connection)
```

- **The worker saves the answer.** It runs whether or not anyone is listening, so a closed tab never loses an exchange. The saved status is `complete`, `stopped` (cancelled; the partial text is kept) or `error`.
- **Cancellation.** A client disconnect (noticed when a heartbeat or frame fails to send) or `POST /conversations/{id}/stop` sets the job's cancel flag. The worker stops at the next pipeline event and closes the Groq stream, so no more tokens are paid for.
- **One run per conversation.** An in-process registry rejects a concurrent answer with `409 conversation_busy` and reports `streaming` on the conversation. It is per process: run one API instance or use sticky sessions.
- **Regenerate / edit** rewind the conversation (delete the old answer and later messages, or replace the question) and rebuild the history from what remains, so follow-up rewriting sees exactly the turns before the question.
- **`done` is always the last frame**, with the saved `message_id`, so clients can Retry stopped or failed answers.

## 5. Evaluation (`evaluation/run_eval.py`)

```powershell
python -m evaluation.run_eval retrieval --strategies legacy hybrid_rerank
python -m evaluation.run_eval generation --limit 10 --negatives 6 --pause 20
```

Reports are written to `evaluation/results/` (gitignored).

### Retrieval (30 in-scope + 8 out-of-scope, top-6, scope ALL)

| Pipeline | doc hit@1 | MRR | topic recall | gate accuracy | latency (CPU) |
|---|---|---|---|---|---|
| v1: dense only, raw chunks | 0.933 | 0.967 | 0.828 | 0.842 | ~8 s |
| **v2: hybrid + MiniLM rerank** | **1.000** | **1.000** | **0.897** | **1.000** | **~2.1 s** |

### Generation (10 in-scope + 6 out-of-scope, `regulatory` mode)

| Metric | Result |
|---|---|
| Answered from documents | 10 / 10 |
| Verified (rules + LLM) | 9 / 10 (1 partially verified after repair) |
| Average verification score | 0.96 |
| Valid citations | 100% |
| Out-of-scope refused | 6 / 6 |
| Latency | median ~4 s, worst 28 s (rate-limit wait + repair) |

`topic_coverage` (0.63) is a keyword overlap with hand-written expected topics. It is a coarse completeness signal, not a correctness metric.

## 6. Tuning knobs

| Setting | Default | Effect |
|---|---|---|
| `RETRIEVAL_STRATEGY` | hybrid | `dense` / `sparse` for experiments |
| `MAX_RETRIEVAL_CHUNKS` | 6 | Passages given to the model |
| `RERANK_MIN_SCORE` | 0.2 | Grounding gate (re-calibrate per reranker) |
| `MAX_CONTEXT_CHARS` | 7000 | Context budget (tokens ≈ chars / 4) |
| `ENABLE_LLM_VERIFIER` | true | Off → rule checks only, saves ~2K tokens/answer |
| `ENABLE_ANSWER_REPAIR` | true | Off → never rewrites, just reports |
| `LLM_REASONING_EFFORT` | low | `medium` improves hard questions at ~2× tokens/latency |
| `ENABLE_FOLLOWUPS` / `ENABLE_LLM_TITLES` | true | Suggested next questions / AI conversation titles (one fast-model call) |
| `SSE_HEARTBEAT_SECONDS` | 10 | Idle heartbeat interval; also bounds how quickly a disconnect is noticed |

## 7. Known limits / next steps

- Scanned PDFs (no text layer) need OCR before ingestion. Without it the ingest job fails
  with "No extractable text" and the document's existing passages are kept.
- Tables are flattened to text; numbers survive but column structure doesn't.
- No date-awareness: superseded circulars are answered like current ones. Add `superseded_by` to the registry and filter.
- Paid Groq tier (or a second provider) removes the 8K TPM ceiling for concurrent users.
