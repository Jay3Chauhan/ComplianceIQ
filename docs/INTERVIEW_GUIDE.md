# ComplianceIQ — AI Engineer Interview Guide (Backend)

Questions an interviewer is likely to ask about this project, with answers grounded in
what the code actually does and the numbers it actually measured. Each design choice
covers **why**, **when to use it**, **when not to**, and **alternatives / trade-offs**.

Use it in three passes: learn the [60-second pitch](#0-the-60-second-pitch) and the
[whiteboard diagram](#whiteboard-diagram), then the deep-dive sections for the areas
your interviewer cares about, then the [rapid-fire round](#21-rapid-fire-round) the
night before.

Related: [RAG_ARCHITECTURE.md](RAG_ARCHITECTURE.md) (how it works),
[API.md](API.md) (endpoints), [../PRODUCTION.md](../PRODUCTION.md) (operations).

---

## Contents

0. [The 60-second pitch](#0-the-60-second-pitch)
1. [RAG fundamentals](#1-rag-fundamentals)
2. [Ingestion: PDFs to chunks](#2-ingestion-pdfs-to-chunks)
3. [Embeddings](#3-embeddings)
4. [Vector database: Qdrant](#4-vector-database-qdrant)
5. [Hybrid retrieval and RRF](#5-hybrid-retrieval-and-rrf)
6. [Reranking](#6-reranking)
7. [The grounding gate](#7-the-grounding-gate-knowing-when-not-to-answer)
8. [Query understanding](#8-query-understanding-rewrite-and-glossary)
9. [Prompting and citations](#9-prompting-and-citations)
10. [Hallucination guard: verifier and repair](#10-hallucination-guard-verifier-and-repair)
11. [LLM choice, rate limits and fallbacks](#11-llm-choice-rate-limits-and-fallbacks)
12. [Streaming and chat reliability](#12-streaming-and-chat-reliability)
13. [API design (FastAPI)](#13-api-design-fastapi)
14. [Persistence and background jobs](#14-persistence-and-background-jobs)
15. [Caching](#15-caching)
16. [Security](#16-security)
17. [Observability](#17-observability)
18. [Evaluation](#18-evaluation)
19. [Performance, scaling and cost](#19-performance-scaling-and-cost)
20. [Debugging stories (behavioural)](#20-debugging-stories-behavioural-questions)
21. [Rapid-fire round](#21-rapid-fire-round)
22. [Glossary](#22-glossary)

---

## 0. The 60-second pitch

> ComplianceIQ answers compliance questions about Indian financial regulation — RBI
> master directions, SEBI master circulars and the Account Aggregator framework — and
> every claim is cited to the document, section and page. It's a RAG system: PDFs are
> cleaned, split into section-aware chunks and indexed in Qdrant with both dense (BGE)
> and sparse (BM25) vectors. A question goes through hybrid search, a cross-encoder
> reranker and a calibrated **grounding gate** that decides whether the corpus covers it
> at all; if not, it says so instead of guessing. The answer is streamed from
> gpt-oss-120b on Groq, then **verified claim by claim** — rule checks for invented
> citations and numbers plus an LLM judge — and repaired once if it fails.
>
> Moving from v1 (dense only) to v2 took correct-document-at-rank-1 from 93% to 100%,
> out-of-scope detection from 84% to 100%, and retrieval latency from 8 s to 2 s on CPU.
> In generation evals 9 of 10 answers fully verified and 6 of 6 out-of-scope questions
> were refused. It ships as a FastAPI + SSE backend with conversations, stop, regenerate,
> edit, admin ingestion jobs and usage analytics, plus a Next.js frontend.

### Whiteboard diagram

```
             ┌────────── offline / admin job ──────────┐
 PDF ─► PyMuPDF (bold flags) ─► drop headers/footers/TOC ─► section tracking
     ─► 900-char chunks (120 overlap) + "Document/Section" header
     ─► BGE-small dense (384-d)  +  BM25 sparse  ─►  Qdrant  (one point, two named vectors)

 question ─► rewrite (only follow-ups) ─► acronym glossary
          ─► dense top-30 ∥ BM25 top-30 ─► RRF fusion
          ─► MiniLM cross-encoder rerank (top-20) ─► gate: best ≥ 0.2 ?
                 no ─► "not found" (regulatory mode) / labelled general answer (auto)
                 yes ─► diversity, top-6 ─► gpt-oss-120b, cited [n], streamed (SSE)
          ─► verifier: rules + Qwen claim check ─► repair once ─► confidence
          ─► saved by a worker thread (survives disconnects) ─► done event
```

---

## 1. RAG fundamentals

**Q: Why RAG instead of fine-tuning or a long-context model?**

- **Why RAG here:** the requirement is *citations to the exact page* and *refusing when
  the documents don't cover it*. Fine-tuning bakes knowledge into weights: it can't cite,
  can't be updated when a circular changes without retraining, and hallucinates
  confidently. RAG keeps the source of truth outside the model, so answers are
  auditable and the corpus can change through an upload.
- **Long context:** the corpus is about 3,500 passages (several thousand pages). Even if
  it fitted, sending it per question is slow and expensive, accuracy drops for facts in
  the middle of long contexts ("lost in the middle"), and the free tier is 8K tokens per
  minute.
- **When fine-tuning *is* right:** teaching a style, format or domain vocabulary, or a
  classification task. It complements RAG (for example, a fine-tuned reranker); it
  doesn't replace retrieval for facts.

**Q: What are the main failure modes of a RAG system?**

1. **Retrieval miss** — the right passage isn't in the top-k (bad chunking, vocabulary
   mismatch, acronyms). Mitigated by hybrid search, the glossary and contextual headers.
2. **Wrong scope** — the question isn't covered but similar-sounding passages are
   retrieved, so the model answers from irrelevant text. Mitigated by the reranker-based
   grounding gate.
3. **Unfaithful generation** — the right passages are retrieved but the model adds facts
   or changes numbers. Mitigated by the prompt contract, the verifier and repair.
4. **Stale or superseded sources** — a known limit; the fix would be `superseded_by`
   metadata.
5. **Operational** — rate limits, model retirement, timeouts. Mitigated by fallbacks,
   retries and readiness checks.

**Q: How do you decide top-k?**

Retrieve wide, then narrow: 30 + 30 candidates go into fusion, 20 into reranking, and 6
into the prompt. Six passages within a 7,000-character budget (about 1,750 tokens) leaves
room for the system prompt, history and answer inside the 8K TPM budget. More passages
raised token cost and gave the model more irrelevant text to cite; fewer dropped topic
recall on multi-part questions.

---

## 2. Ingestion: PDFs to chunks

**Q: Walk me through ingestion.**

`ingestion/pipeline.py` is the single entry point shared by the CLI, the admin API and
background jobs:

1. **Extract** with PyMuPDF `get_text("dict")`, which keeps font flags, so bold lines can
   be detected as headings. pdfplumber is the fallback.
2. **Clean** (`text_cleaning.py`): remove running headers and footers (edge lines that
   repeat on at least 30% of pages), table-of-contents pages and footnote markers;
   re-flow wrapped lines; de-hyphenate.
3. **Track sections** (`SectionTracker`): bold lines become headings and
   `CHAPTER`/`PART` lines become chapters, so every block carries a path like
   `Chapter III › 16. Periodic updation`.
4. **Chunk** at 900 characters with 120 overlap, splitting on lines, then clauses, then
   sentences. Each chunk inherits the section at its position.
5. **Contextual header**: the *embedded* text is `Document: … / Section: …` plus the
   chunk; the stored payload keeps the clean chunk for display.
6. **Embed** dense and sparse and upsert both into one Qdrant point with deterministic
   IDs.

**Q: Why 900 characters with 120 overlap? The original spec said 500/50.**

- Regulatory clauses are long: a rule, its conditions and its exceptions often span 600
  to 900 characters. At 500, conditions got split from the rule they qualify, and the
  answer cited half a clause.
- Overlap (about 13%) keeps a sentence that straddles a boundary retrievable from either
  side without duplicating too much.
- **Trade-off:** bigger chunks mean fewer, denser passages (better context per citation)
  but less precise matching and more tokens per passage. Six passages × 900 characters
  fits the context budget.
- **When to change:** FAQ-style or very short documents want smaller chunks; tables or
  code want structure-aware chunking instead of character counts. Any change requires a
  full re-index (`--recreate`).

**Q: What is the contextual header and why does it help?**

A clause like "the entity shall update KYC every two years" doesn't say *which* entity or
*which* direction. Prepending `Document: RBI Master Direction on KYC / Section: Periodic
updation` to the embedded text lets both dense and BM25 match on document and section
words. It is a cheap version of Anthropic's "contextual retrieval" (which generates a
per-chunk summary with an LLM). The header isn't stored in the payload, so citations
show clean text.

**Q: Why deterministic chunk IDs?**

`uuid5(filename:seq)` means re-ingesting a document overwrites the same points instead of
duplicating them, and the pipeline deletes a document's old vectors before upserting.
Ingestion is idempotent, so a failed job can simply be retried.

**Q: What happens with a scanned PDF?**

There is no text layer, so there are no chunks. The pipeline now returns `failed` with
"No extractable text… OCR is not supported" **before** touching the index, so replacing
a good document with an unreadable file doesn't wipe its existing passages. The fix for
real scanned input is an OCR step (Tesseract, or a cloud document-AI service) before
cleaning.

**Q: How are tables handled?**

They are flattened to text: numbers survive but column structure doesn't. For
table-heavy documents you'd extract tables separately (pdfplumber or Camelot), store them
as Markdown chunks, and possibly use a table-aware embedding or row-level chunks. This
is a documented limit.

---

## 3. Embeddings

**Q: Why `BAAI/bge-small-en-v1.5`?**

- **Why:** strong retrieval quality for its size (384 dimensions, about 33M parameters),
  runs locally on CPU, no per-token cost, no rate limits and no data leaving the server.
  The 384-d vectors keep the Qdrant free tier comfortable.
- **When not:** multilingual corpora (use `bge-m3` or `multilingual-e5`), very long
  passages, or when you can afford a larger model (`bge-large`, or OpenAI/Voyage/Cohere
  embeddings) for a few points of recall.
- **Trade-off:** small models lose nuance on paraphrases. Hybrid search and a
  cross-encoder reranker recover most of that, which is cheaper than a bigger
  embedding model.

**Q: What prefix convention does BGE use?**

BGE v1.5 embeds passages **without** a prefix and queries **with** the instruction
`"Represent this sentence for searching relevant passages: "` (`QUERY_INSTRUCTION` in
config). The `query:` / `passage:` convention in the original spec belongs to the E5
family; using the wrong model's convention silently degrades retrieval, which is worth
checking in every RAG codebase.

**Q: Cosine, dot product or Euclidean?**

Embeddings are L2-normalised and the collection uses cosine. On normalised vectors cosine
and dot product rank identically; cosine is the safe default when you're unsure whether
vectors are normalised.

**Q: Why run embeddings locally instead of using an API?**

Zero marginal cost, no network hop at query time, no data-processing agreement needed for
regulated content, and deterministic versions. The costs are RAM (torch plus three models
need a 2 GB+ instance) and cold-start time. The Docker image bakes the models in, so
there are no downloads at startup.

---

## 4. Vector database: Qdrant

**Q: Why Qdrant?**

- **Why:** native **named vectors** (dense and sparse in one point), built-in **RRF
  fusion** in one `query_points` call, payload indexes for filters (category, doc_id),
  a managed free cluster, and a good Python client.
- **Alternatives:**
  - **pgvector:** one database for everything and transactional; hybrid search needs
    manual SQL plus `tsvector`; HNSW is fine up to millions of rows. A great choice if
    you already run Postgres.
  - **Pinecone:** fully managed with sparse-dense support; proprietary and paid.
  - **Weaviate / Milvus:** similar features; heavier to operate.
  - **FAISS:** a library, not a database: no filters, persistence or updates without
    work. Good for offline experiments.
  - **Chroma:** easy local prototyping; fewer production features.
- **When Qdrant isn't needed:** under about 50K chunks with no hybrid requirement,
  pgvector or even in-memory FAISS is simpler.

**Q: How does the vector index work (HNSW)?**

HNSW builds a multi-layer proximity graph: search starts at a sparse top layer and greedily
descends to denser layers. It is approximate — recall versus speed is tuned with `m`,
`ef_construct` and query-time `ef`. Filters are applied during graph traversal using
payload indexes, so filtered search stays fast (no post-filtering that returns fewer than
k results).

**Q: How is category filtering done?**

As a Qdrant `Filter` on the indexed `category` payload field, passed to **both**
prefetches, so the dense and BM25 candidate lists are filtered before fusion.

---

## 5. Hybrid retrieval and RRF

**Q: Why hybrid search?**

Dense and sparse fail differently:

- **Dense** handles paraphrase ("customer verification" ↔ "KYC process") but is weak on
  exact tokens: circular numbers (`RBI/2022-23/111`), "Annex II", "₹ 2 crore",
  section numbers.
- **BM25** nails exact terms and rare words but misses synonyms.

Together, doc hit@1 went from 0.933 to 1.0 and MRR from 0.967 to 1.0 on the eval set.

**Q: What is Reciprocal Rank Fusion and why not a weighted score sum?**

RRF scores each document as Σ 1 / (k + rank_i) across the result lists (k is about 60).
It only uses **ranks**, so you don't have to normalise incomparable scores (cosine in
[−1, 1] vs unbounded BM25). It is robust and needs no tuning. A weighted sum needs score
normalisation and a tuned α that drifts when the corpus changes. **When to prefer
weighted:** when you have labelled data to learn the weight, or one retriever is much
stronger.

**Q: When is hybrid not worth it?**

Conversational or paraphrase-heavy corpora with few identifiers, or tiny corpora where a
reranker over dense results already reaches the ceiling. It costs a second index and a
second query (cheap in Qdrant; one round trip).

---

## 6. Reranking

**Q: What does the reranker do and why is it the biggest win?**

The embedding model is a **bi-encoder**: the query and passage are encoded separately,
so it's fast and pre-computable, but it can't model their interactions. The
**cross-encoder** (`ms-marco-MiniLM-L-6-v2`) reads query and passage *together* and
outputs a relevance score. It is far more accurate but costs one forward pass per
pair, so it's only applied to the top 20 fused candidates.

Its sigmoid output is also a **calibrated-ish probability of relevance**, which is what
makes the grounding gate possible (section 7). Raw cosine similarity isn't comparable
across queries.

**Q: Latency cost?**

About 20 passages × MiniLM-L6 on CPU is a few hundred milliseconds. Overall, v2 retrieval
(about 2.1 s) is *faster* than v1 (about 8 s) because v1 used the larger embedding path
and no caching. Upgrades: `bge-reranker-base` (better and slower), Cohere Rerank (API),
or a GPU.

**Q: What does the reranker see?**

`doc name + section + text`, so a passage from the right document and section gets
credit even when the clause itself is terse.

---

## 7. The grounding gate: knowing when not to answer

**Q: How does the system decide a question is out of scope?**

The best reranker score must be at least `RERANK_MIN_SCORE` (0.2). Calibrated on the eval
set:

| | Best rerank score |
|---|---|
| Lowest in-scope question | 0.54 |
| Highest out-of-scope question (e.g. GST rate) | 0.08 |

0.2 sits in the gap with margin on both sides; gate accuracy is 1.0 (v1's cosine
threshold of 0.35 got 0.842). **Re-calibrate whenever the reranker changes**
(`python -m evaluation.run_eval retrieval`).

**Q: Why gate on the reranker rather than on embedding similarity?**

Cosine scores from a bi-encoder cluster in a narrow band and aren't comparable across
queries: an off-topic question about "rates" can still score 0.6 against interest-rate
passages. The cross-encoder's score separates "related words" from "actually answers
this", which is exactly the decision the gate makes.

**Q: What happens when the gate fails?**

It depends on the **answer mode**:

- `regulatory`: return the fixed "not found" answer with **no LLM call** (no cost, no
  hallucination risk).
- `auto` (default): a general-knowledge answer, clearly labelled as not from the
  documents.
- `general`: skips retrieval entirely.

There's a second, softer check: if the gate passes but the model writes the refusal
sentence *without citations* (passages related but not answering it, such as "What is a
SIP?"), `auto` falls back to a general answer and streaming clients get a
`revision{reason:"general_fallback"}` event.

---

## 8. Query understanding: rewrite and glossary

**Q: Why only rewrite follow-up questions?**

"What about low-risk ones?" can't be retrieved on its own. With history present and a
short or pronoun-heavy question, the fast model rewrites it into a standalone query. A
first question isn't rewritten: rewriting costs about 0.4 s plus tokens on every query,
and LLM rewrites sometimes *drop* exact terms (circular numbers) that BM25 needs. Only
the retrieval query changes; the user's wording is still what the answer model sees.

**Q: What does the glossary do?**

It expands about 55 Indian-regulation acronyms (KYC, CKYCR, FLDG, KFS, NOF, FIU, LSP…) to
their long forms in the search query. Documents use both forms inconsistently; expansion
helps BM25 match either and gives the reranker more signal. It is deterministic, free
and testable, unlike asking an LLM to expand.

**Q: Why not HyDE or multi-query expansion?**

Both add an LLM call per question (latency and TPM budget) and HyDE can hallucinate a
hypothetical answer that biases retrieval toward wrong passages. With hybrid search,
reranking and 100% hit@1 on the eval set, the extra cost isn't justified. They'd be
worth trying if recall dropped on a bigger, messier corpus.

---

## 9. Prompting and citations

**Q: What's in the prompt contract?**

(`llm/prompt_templates.py`)

- Passages are numbered `[1]…[6]` inside a `<sources>` block with document, circular,
  section and page.
- Every factual sentence needs an `[n]` citation; figures, time limits and amounts must
  be **copied exactly**.
- Text inside `<sources>` is **data, not instructions** (prompt-injection guard).
- If the passages are insufficient, write the exact refusal sentence; partial coverage
  goes under "Not covered in the loaded documents".
- Low reasoning effort, hidden reasoning, and output normalisation (`【n】` and
  `[n†…]` are rewritten to `[n]`, non-breaking characters to ASCII).

**Q: Why `[n]` markers instead of asking the model to write the citation text?**

Numbers are short, unambiguous and machine-checkable: the verifier can confirm `[7]`
doesn't exist when 6 passages were given, and the UI maps each `[n]` to the exact chunk,
page and section. Free-text citations get paraphrased and can't be validated.

**Q: How do you defend against prompt injection from documents?**

The sources are wrapped and labelled as data, the system prompt says to ignore
instructions inside them, and the verifier catches claims not supported by the passages.
Documents are uploaded only by admins, which limits the attack surface. A stronger setup
would add an input classifier or strip instruction-like text at ingestion.

---

## 10. Hallucination guard: verifier and repair

**Q: How does the verifier work?**

(`llm/verifier.py`)

1. **Rule checks** (free and deterministic):
   - citations to passages that don't exist;
   - factual sentences without a citation;
   - numbers in the answer that appear in no passage (digits and small number words).
2. **LLM claim check:** each sentence (up to 14) is judged supported or unsupported
   against the passages by the fast model, as JSON.
3. **Score** = supported / claims, ×0.75 if there are unsupported numbers, ×0.5 if
   there are invalid citations:
   - `verified`: score ≥ 0.8 with no number or citation issues;
   - `partially_verified`: score ≥ 0.5;
   - otherwise `unverified`.
4. **Repair:** if anything failed, the answer model gets the list of problems and
   rewrites once. The rewrite is kept only if its score isn't lower. Streaming clients
   get a `revision` event.
5. **Confidence:**
   - `high`: verified and gate score ≥ 0.5;
   - `medium`: otherwise for grounded answers;
   - `low`: general mode or unverified.

**Q: Why both rules and an LLM judge?**

Rules are cheap, deterministic and catch the most damaging errors in compliance (wrong
numbers, fake citations) with no false negatives on those patterns. The LLM judge catches
semantic unsupported claims that rules can't. If the judge is rate-limited, the rules
still run (`method: "rules"`), so verification degrades gracefully instead of vanishing.

**Q: Isn't LLM-as-judge unreliable?**

It can be lenient, inconsistent or biased toward fluent text. Mitigations here:

- a different model from the answerer, so it doesn't grade its own homework;
- sentence-level judgments rather than one holistic score;
- JSON output;
- deterministic rules for numbers and citations.

It is a guard, not a guarantee: the UI shows verification status and confidence so users
know when to check the source.

**Q: Why only one repair pass?**

Each pass costs about 3–4K tokens and seconds of latency. In evals one pass fixed most
issues (9 of 10 verified, the last partially verified). Unbounded loops risk
oscillation and rate limits.

---

## 11. LLM choice, rate limits and fallbacks

**Q: Why Groq, and why these models?**

- **Groq:** very fast inference (hundreds of tokens per second, good for streaming UX),
  an OpenAI-compatible API and a free tier.
- **Answers:** `openai/gpt-oss-120b` is the strongest model available on the key, with
  low reasoning effort for latency.
- **Rewrite and verification:** `qwen/qwen3.8-27b` is non-reasoning (about 0.4 s),
  supports JSON mode, and has a **separate rate-limit bucket**.
- **Fallbacks:** `openai/gpt-oss-20b`, then Qwen, on 429 or 404.

**Q: How do you live within 8K tokens per minute per model?**

- **Split roles across models:** one verified answer costs about 3–4K tokens on the
  answer model plus about 2K on the verifier. Separate buckets mean verification doesn't
  starve answers.
- **Context budget:** 7,000 characters (about 1,750 tokens) of passages; history is
  truncated.
- **No LLM call** for out-of-scope questions in regulatory mode.
- **Caching:** identical questions hit a 10-minute TTL cache.
- **Reasoning allowance:** Groq reserves `max_completion_tokens` against TPM, so only
  reasoning models get the extra allowance.
- **Non-essential calls fail silently:** follow-up suggestions and titles never block or
  break an answer.

**Q: What happens when a model is retired?**

Groq returns 404 `model_not_found` and the client moves to the next fallback.
`python -m scripts.check_llm` lists what the key can use. `/ready` reports LLM
configuration.

**Q: Temperature?**

Low (around 0.1) for factual compliance answers: you want reproducibility and exact
figures, not creativity.

---

## 12. Streaming and chat reliability

**Q: Why SSE instead of WebSockets?**

- **SSE:** one-way server-to-client stream over plain HTTP. It works through proxies and
  load balancers, and is simple to authenticate (normal headers via the BFF). The client
  only sends one question per answer, so bidirectional is unnecessary. Stop is a separate
  `POST /conversations/{id}/stop`.
- **WebSockets:** bidirectional and stateful. Worth it for real-time collaboration, voice,
  or many small client messages, at the cost of sticky connections and custom auth and
  reconnect logic.
- **Polling:** the simplest option, but terrible for token streaming.

**Q: Describe the event protocol.**

Typed JSON events, in order:

- `conversation`
- `status` (stages)
- `sources`
- `token`…
- optional `revision`
- `verification`
- `followups`
- `done`

`done` is **always the last frame** and carries the saved `message_id`, so the client
knows the final state even after a stop or error.

**Q: What if the browser disconnects mid-answer?**

A **worker thread owns persistence**: it runs the pipeline and saves the result whether or
not anyone is listening, so a closed tab never loses an exchange. The SSE relay only
forwards events from a queue. Saved status is `complete`, `stopped` (partial text kept)
or `error`.

**Q: How does cancellation work, and why does it matter for cost?**

A client disconnect (noticed when a heartbeat or frame fails to send) or the stop endpoint
sets the job's cancel flag. The worker checks it at the next pipeline event and **closes
the Groq stream**, so you stop paying for tokens nobody will read.

**Q: Why heartbeats?**

Proxies (nginx, Render, Vercel) kill idle connections after 30–60 s, and the verification
phase can be silent for several seconds. A `: ping` comment every 10 s idle keeps the
connection alive **and** bounds how quickly a disconnect is detected.

**Q: How do you stop two answers running in one conversation?**

An in-process **run registry** reserves the conversation; a concurrent request gets
`409 conversation_busy`, and the conversation reports `streaming: true` so a reloaded tab
can poll. The limitation is that it's per process: with several instances you need
sticky sessions or a Redis lock (`SET key NX PX`).

**Q: How do regenerate and edit work?**

They rewind the conversation:

- **Regenerate** deletes the old answer and any later messages.
- **Edit** replaces the question.

Both then rebuild history from what remains, so follow-up rewriting sees exactly the turns
before the question.

---

## 13. API design (FastAPI)

**Q: Why FastAPI?**

- Async I/O for streaming.
- Pydantic validation and automatic OpenAPI docs.
- Dependency injection for auth and rate limits.

**When not:** Django suits heavy admin or ORM needs; Go or Rust suit very high RPS. The
heavy work here is ML inference and an external LLM, not Python request overhead.

**Q: Async routes calling CPU-bound models — isn't that a problem?**

Yes, if done naively: running an embedding or reranker inference inside an `async def`
blocks the event loop and freezes every other request. CPU-bound and blocking calls go
through `asyncio.to_thread` or the worker thread, and ingestion runs on a dedicated
single-worker executor.

**Q: How are errors and versions handled?**

- **Versioning:** routes live under `/api/v1` and legacy routes are kept for old clients.
- **Error envelope:** every error has the shape
  `{error:{code, message, request_id}}` with a stable machine-readable `code`
  (`conversation_busy`, `rate_limited`, `document_exists`…), so clients branch on
  codes, not messages.
- **Request IDs:** a middleware assigns `X-Request-ID` and `X-Response-Time-ms`, logged
  with every line.

**Q: Why a BFF (backend-for-frontend) in Next.js?**

The browser never sees the API key or the admin key. The Next.js server adds `X-API-Key`,
`X-User-Id` (from an httpOnly cookie) and, for admins, `X-Admin-Key` after checking a
signed session cookie. It also allowlists which paths are proxied. Streaming passes
through unbuffered, and admin uploads bypass the proxy's 10 MB body buffering.

---

## 14. Persistence and background jobs

**Q: What do you store, and why SQLAlchemy?**

Tables:

- `conversations`, `messages` (with sources, verification, follow-ups);
- `feedback` (with reasons);
- `query_logs` (every question's mode, gate score, verification, model, timings);
- `ingest_jobs`.

SQLAlchemy lets the same code run on **SQLite** (zero-ops local or single instance) and
**Postgres** (multi-instance) by changing `DATABASE_URL`.

**Q: How are schema changes handled without Alembic?**

`create_all` plus a lightweight auto-migration that adds new nullable columns in place.
That's enough while changes are additive. Renames, type changes or data migrations need
Alembic; that's the next step for a team.

**Q: Why a ThreadPoolExecutor with one worker for ingestion instead of Celery?**

- **Why:** ingestion is rare and CPU-heavy. One worker keeps embedding from starving
  request handling. Job state lives in the database, so the UI polls `/admin/jobs`. On
  startup, orphaned jobs from a crashed process are marked failed.
- **When to switch to Celery, RQ or Arq:** multiple API instances, retries with backoff,
  scheduled re-indexing, or jobs that must survive restarts. These need Redis or a broker.

---

## 15. Caching

**Q: What's cached and how is it invalidated?**

Retrieval results and answers for identical (query, filters) keys are kept in a 10-minute
TTL cache. Ingestion, metadata edits, deletes and the admin "clear cache" action
invalidate it.

**Q: Trade-offs?**

- It's in-memory and per instance, so it's lost on restart and not shared. Redis fixes
  both.
- Exact-match keys miss paraphrases. A **semantic cache** (embed the query and reuse
  answers above a similarity threshold) hits more, but risks serving an answer to a
  subtly different question, which is dangerous in compliance. Keep the threshold very
  high or don't use it.

---

## 16. Security

**Q: How is the API authenticated?**

- **Service-to-service:** `X-API-Key`, compared with `hmac.compare_digest` (constant time,
  no timing leaks). In production the API refuses to start open
  (`503 auth_not_configured`).
- **Admin routes:** `X-Admin-Key`, disabled in production if unset.
- **Users:** `X-User-Id` comes from the *trusted* caller (the BFF) and is validated by
  regex. It scopes conversations and feedback. Today it's an anonymous cookie id; real
  sign-in would put the auth provider's user id there.

**Q: How does the admin console stay secure?**

- An admin password produces an **HMAC-signed, expiring, httpOnly, SameSite=Strict**
  cookie (8 hours). Changing the password invalidates all sessions.
- Sign-in is throttled per IP.
- The admin proxy checks the cookie, rejects cross-origin non-GET requests, allowlists
  paths, and only then attaches the server-side admin key.

**Q: Rate limiting?**

A sliding-window limiter (per API key and user, default 30 questions per minute) returns
`429` with `Retry-After`. It's in-memory per instance; multi-instance deployments need
Redis or a gateway limiter. It also protects the Groq budget.

**Q: Upload safety?**

- Filename sanitisation (`safe_filename`, so `../../etc/passwd` becomes `passwd.pdf`).
- PDF type check (`415`), size limit (`413`, 50 MB), empty-file check, and `409` unless
  `replace` is set.
- Admin-only access.

**Q: Other security points?**

- Secrets only come from environment variables; `.env` is gitignored, and API keys never
  use `NEXT_PUBLIC_`.
- CORS is restricted (or unused, since calls are server-to-server).
- Prompt-injection guard (section 9).
- Answers are labelled assistive, not legal advice.

---

## 17. Observability

**Q: How would you debug a bad answer reported by a user?**

1. Feedback (thumbs-down plus a reason) is stored with the message id.
2. `query_logs` holds mode, gate score, retrieved chunks, verification result and
   unsupported claims, model used and per-stage timings for that request.
3. Correlate logs by `request_id`.
4. Reproduce with `POST /search`, which returns the retrieval results, gate score and
   timings without generating.
5. Add the question to `evaluation/test_questions.json` so it never regresses.

**Q: Health versus readiness?**

- **`/health`:** liveness. The process is up; cheap enough for load balancers to call
  often.
- **`/ready`:** readiness. It checks Qdrant (with vector count), the database, model
  warm-up and LLM configuration, returning 503 when degraded. Use it for alerts and
  traffic gating, **not restarts**: restarting because Groq is rate-limited won't help.

**Q: What's in the admin stats?**

Over the chosen window:

- query count, mode mix, grounded rate;
- verification breakdown and revised answers;
- errors, latency p50 and p95;
- feedback ratio and recently unanswered questions (candidates for new documents);
- index status and document coverage.

---

## 18. Evaluation

**Q: How do you evaluate retrieval?**

`python -m evaluation.run_eval retrieval` on 30 in-scope and 8 out-of-scope questions with
expected documents and topics:

- **doc hit@1:** is the expected document the top result? (v2: 1.0)
- **MRR:** mean of 1/rank of the first correct document. (1.0)
- **Topic recall:** fraction of expected topics present in the top-6. (0.897)
- **Gate accuracy:** in-scope passes and out-of-scope is blocked. (1.0)
- **Latency:** about 2.1 s on CPU.

**Q: And generation?**

`run_eval generation` measures:

| Metric | Result |
|---|---|
| Answered from documents | 10 / 10 |
| Fully verified | 9 / 10 |
| Average verification score | 0.96 |
| Valid citations | 100% |
| Out-of-scope refused | 6 / 6 |
| Latency | median about 4 s |

The `topic_coverage` keyword score (0.63) is a coarse completeness signal, not a
correctness metric — say so if asked.

**Q: What about RAGAS?**

RAGAS metrics, and how each maps to this system:

- **Faithfulness:** claims supported by context. This is what the verifier approximates
  online.
- **Answer relevancy.**
- **Context precision:** are the retrieved chunks relevant and ranked well?
- **Context recall:** do they cover the ground truth?

RAGAS uses an LLM judge, so it is costly on a free tier and noisy on small sets. The
in-house metrics are deterministic and cheap to run on every change; RAGAS is a periodic
cross-check.

**Q: How would you grow the eval set?**

From production: thumbs-down answers, unanswered questions and partially verified
answers, each labelled with the expected document, page and key facts. Keep separate
in-scope and out-of-scope sets, and track metrics per regulator.

**Q: Offline versus online evaluation?**

- **Offline evals** gate changes: chunking, models, thresholds.
- **Online signals** show real-world drift: feedback ratio, grounded rate,
  verification mix, unanswered rate. An A/B test of a new reranker would compare those.

---

## 19. Performance, scaling and cost

**Q: Where does the latency go?**

| Stage | Time |
|---|---|
| Retrieval (embed, hybrid query, rerank) | about 2 s on CPU (cached: about 0 s) |
| Time to first token | about 1–2 s more |
| Full answer | a few seconds on Groq |
| Verification and optional repair | 1–5 s |

Median end to end is about 4 s; the worst case is about 28 s (rate-limit wait plus
repair). Streaming plus `status` events make the wait feel shorter.

**Q: How would you scale to many users?**

1. **Groq tier first:** 8K TPM per model is the real ceiling. Move to a paid tier or add
   a second provider.
2. **Stateless instances:** move the run registry, rate limiter and cache to Redis, the
   database to Postgres, and jobs to a broker. Until then, use sticky sessions.
3. **Model serving:** run the embedder and reranker on a GPU or a separate inference
   service with batching; scale API pods independently.
4. **Qdrant:** a bigger cluster or replicas; quantisation (scalar or binary) cuts memory.

**Q: What does an answer cost?**

On paid pricing it's about 4–6K tokens per verified answer across two models (fractions
of a cent on Groq). Embedding and reranking are free (local). The biggest levers are:

- no LLM call for out-of-scope questions;
- caching;
- the context budget;
- turning off the LLM verifier (rules only, saves about 2K tokens);
- stopping generation on disconnect.

---

## 20. Debugging stories (behavioural questions)

Use the STAR structure: situation, task, action, result.

- **"Tell me about improving a model's accuracy."** v1 used dense search with a cosine
  threshold of 0.35: gate accuracy was 0.842 and it answered GST questions from
  interest-rate passages. I added BM25 hybrid search, a cross-encoder reranker, and
  calibrated the gate on the reranker's score (in-scope minimum 0.54, out-of-scope
  maximum 0.08, threshold 0.2). Gate accuracy reached 1.0, hit@1 went from 0.933 to 1.0,
  and latency dropped from 8 s to 2 s.
- **"A time you prevented a bad output."** Answers occasionally changed figures (for
  example, a time limit). I added a rule that flags numbers absent from every passage,
  weighted it in the verification score, and added a repair pass. 9 of 10 eval answers
  now fully verify, the rest partially, and none are unverified.
- **"An operational incident."** Answers began failing with `model_not_found`: Groq had
  retired a model. I added ordered fallbacks on 404/429, a `check_llm` script and an
  LLM check in `/ready`.
- **"A distributed-systems bug."** Streams arrived all at once in production because a
  proxy buffered `text/event-stream`. Fixed with `X-Accel-Buffering: no`,
  `Cache-Control: no-transform` and heartbeats. Separately, a closed tab lost answers
  until persistence moved into a worker thread that outlives the connection.
- **"Silent failure."** Uploading a scanned PDF "succeeded" with 0 chunks and would have
  replaced a good document's vectors with nothing. The pipeline now fails with a clear
  reason *before* touching the index, with a unit test.

---

## 21. Rapid-fire round

| Question | Short answer |
|---|---|
| Bi-encoder vs cross-encoder? | Bi: encode separately, fast, pre-computable (retrieval). Cross: encode the pair, accurate, slow (reranking the top-k). |
| Why normalise embeddings? | Cosine equals dot product, and magnitude doesn't skew scores. |
| What is RRF's k? | A smoothing constant (about 60) that limits the dominance of top ranks. |
| Chunk overlap purpose? | Facts on a boundary stay retrievable from either side. |
| Why deterministic chunk IDs? | Idempotent re-ingestion: overwrite instead of duplicate. |
| What does the grounding gate prevent? | Answering out-of-scope questions from loosely related passages. |
| Why not threshold on cosine? | Bi-encoder scores aren't comparable across queries; the reranker's are. |
| Why number citations? | Machine-checkable and mappable to exact chunks in the UI. |
| What does the verifier check? | Invalid citations, uncited claims, unsupported numbers, and an LLM claim check. |
| SSE vs WebSocket? | SSE: one-way, plain HTTP, proxy-friendly; enough for token streams. |
| Why heartbeats? | Keep proxies from closing idle streams; detect disconnects. |
| Why a worker thread for chat? | Persistence survives client disconnects; cancellation closes the LLM stream. |
| 409 `conversation_busy`? | One active answer per conversation (per-process registry). |
| `/health` vs `/ready`? | Liveness vs dependencies; alert on `/ready`, don't restart on it. |
| Why a BFF? | Keys stay server-side; path allowlist; user identity from an httpOnly cookie. |
| Constant-time compare? | `hmac.compare_digest` stops timing attacks on API keys. |
| Sliding window vs token bucket? | Sliding: exact per-window counts. Token bucket: allows bursts with a steady refill. Both fine; sliding is simpler to reason about. |
| Biggest scaling bottleneck? | LLM tokens per minute, then in-process state (registry, limiter, cache). |
| Why local embeddings? | No cost, no rate limit, data stays in, deterministic version. |
| What would you build next? | OCR, table extraction, `superseded_by` date-awareness, Redis for shared state, real auth, growing the eval set from feedback. |
| HNSW tuning knobs? | `m` (graph degree), `ef_construct` (build quality), `ef` (search breadth vs speed). |
| Lost in the middle? | LLMs under-use facts in the middle of long contexts; keep the context short and ranked. |
| Temperature for compliance? | Low (about 0.1): reproducible, exact figures. |
| How do you know retrieval regressed? | Run the retrieval eval in CI; watch hit@1, MRR and gate accuracy. |

---

## 22. Glossary

| Term | Meaning |
|---|---|
| RAG | Retrieval-augmented generation: retrieve relevant text, then generate an answer grounded in it. |
| Chunk / passage | A slice of a document that is embedded and retrieved as a unit. |
| Dense vector | Learned embedding capturing meaning (BGE, 384-d). |
| Sparse vector / BM25 | Term-weighted bag of words; exact-match strength. |
| RRF | Reciprocal Rank Fusion: combine ranked lists by Σ 1/(k + rank). |
| Cross-encoder | Model scoring a (query, passage) pair jointly; used for reranking. |
| Grounding gate | Threshold on the best rerank score that decides whether the corpus covers the question. |
| hit@1 / MRR | Is the correct document first / mean reciprocal rank of the first correct document. |
| Faithfulness | Fraction of answer claims supported by the retrieved context. |
| TPM | Tokens per minute: the provider's rate limit. |
| SSE | Server-Sent Events: one-way HTTP streaming of text events. |
| BFF | Backend-for-frontend: a server layer that owns secrets and shapes the API for one UI. |
| TTL cache | Entries expire after a fixed time (10 minutes here). |
| Idempotent | Running the same operation twice has the same effect as once. |
