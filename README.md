# ComplianceIQ

Grounded Q&A over Indian financial regulations — RBI Master Directions, SEBI master
circulars and the Account Aggregator framework. Every answer cites the document,
circular number, section and page, and is checked claim-by-claim against the
sources before it reaches the user.

## What it does

- **Cited answers** — `[n]` markers map to the exact passage, section and page.
- **Says "not found"** instead of guessing when the documents don't cover a question
  (100% of out-of-scope test questions refused).
- **Verifies itself** — rule checks (invented citations, uncited claims, numbers not in the
  sources) plus an LLM claim check; failing answers are repaired once.
- **Hybrid retrieval** — dense BGE + BM25 fused in Qdrant, cross-encoder rerank, grounding gate.
- **Conversations, feedback, search, document browser, admin uploads** via a versioned REST + SSE API.
- **Reliable chat** — answers are saved server-side even if the browser disconnects; stop,
  regenerate/retry, edit-and-resend, follow-up suggestions, AI titles and Markdown/JSON export.
- **Next.js web app** in [`web/`](web/README.md) — streaming chat with citations, a sources
  panel, verification badges, history, document library and passage search. A Streamlit UI
  (`frontend/`) is kept for quick local use.

| Metric (eval set) | v1 | v2 |
|---|---|---|
| Correct document at rank 1 | 93% | **100%** |
| Out-of-scope detection | 84% | **100%** |
| Answers verified against sources | – | **90%** (100% verified or partial) |
| Retrieval latency (CPU) | ~8 s | **~2 s** |

Details: [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md).

## Architecture

```
PDF → clean + sections → chunks w/ contextual header → BGE dense + BM25 sparse → Qdrant

question → rewrite (follow-ups) → glossary → hybrid RRF → MiniLM rerank → gate
         → gpt-oss-120b (cited, streamed) → verifier (rules + Qwen) → repair → answer
```

| Layer | Choice |
|---|---|
| LLM | Groq `openai/gpt-oss-120b` (answers), `qwen/qwen3.8-27b` (rewrite, verification), `gpt-oss-20b` fallback |
| Embeddings | `BAAI/bge-small-en-v1.5` (local) + `Qdrant/bm25` sparse (fastembed) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) |
| Vector DB | Qdrant Cloud, collection `regulations_v2` |
| API | FastAPI, SSE streaming |
| Persistence | SQLAlchemy — SQLite by default, Postgres via `DATABASE_URL` |
| UI | Next.js 16 + Tailwind + shadcn/ui (`web/`); Streamlit (`frontend/`) |

## Repo layout

```
api/            FastAPI app: v1 routes, legacy routes, auth, errors, middleware, services
db/             SQLAlchemy models + repository (conversations, messages, feedback, logs, jobs)
ingestion/      PDF parsing, cleaning, sections, chunking, embedding, registry, pipeline
retrieval/      hybrid search, reranker, glossary, catalog, cache
llm/            Groq client, prompts, query rewriter, verifier
rag/            end-to-end pipeline (answer + stream)
web/            Next.js frontend (BFF proxy, chat, library, search)
frontend/       Streamlit app
evaluation/     retrieval + generation eval harness and test set
scripts/        smoke test, model check, debugging helpers
docs/           RAG architecture, API reference, Next.js frontend spec
tests/          unit tests (+ live tests with RUN_INTEGRATION=1)
```

## Quick start (Windows / PowerShell)

Use Python 3.11–3.13 (3.14 breaks some native wheels).

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

copy .env.example .env      # fill GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY, API_KEYS
python -m scripts.check_llm # confirms the Groq models are reachable

# PDFs go in data/documents/, metadata in data/document_registry.json
python -m ingestion.run_ingestion            # add --recreate to rebuild the collection

uvicorn api.main:app --reload --port 8000    # http://localhost:8000/docs

# second terminal: the web app (http://localhost:3000)
cd web; npm install
copy .env.example .env.local   # COMPLIANCEIQ_API_URL, COMPLIANCEIQ_API_KEY=<one of API_KEYS>
npm run dev

# or the Streamlit UI
$env:COMPLIANCEIQ_API_KEY="<one of API_KEYS>"
streamlit run frontend/app.py
```

Check everything end to end:

```powershell
python scripts/smoke_test.py --api-key <key> --admin-key <admin-key>
```

## Using the API

```bash
curl -N http://localhost:8000/api/v1/chat/stream \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"How often must KYC be updated for high-risk customers?"}'
```

Full reference, SSE protocol and error codes: [docs/API.md](docs/API.md).

## Tests and evaluation

```powershell
pytest -q                                              # unit tests, no network
$env:RUN_INTEGRATION="1"; pytest -q tests/test_retrieval.py   # live Qdrant
python -m evaluation.run_eval retrieval --strategies legacy hybrid_rerank
python -m evaluation.run_eval generation --limit 10 --negatives 6
```

## Deployment and operations

See [PRODUCTION.md](PRODUCTION.md).

## Safety note

ComplianceIQ answers only from the documents loaded into it and is an assistive tool.
Validate conclusions with your compliance/legal process and the regulator's current
circulars.

## License

MIT. See `LICENSE`.
