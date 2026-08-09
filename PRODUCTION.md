# ComplianceIQ — Production Guide

This document covers architecture, RAG quality settings, local ops, deployment, security, and testing.

## What you need (accounts / keys)

| Item | Required? | Where | Notes |
|------|-----------|--------|------|
| Groq API key | Yes | [console.groq.com](https://console.groq.com) | Free tier works for demos |
| Qdrant Cloud cluster | Yes | [cloud.qdrant.io](https://cloud.qdrant.io) | Free tier is fine for personal projects |
| Render (or similar) | For API deploy | [render.com](https://render.com) | Needs enough RAM for torch + BGE (~2GB+) |
| Streamlit Community Cloud | For UI deploy | [share.streamlit.io](https://share.streamlit.io) | Points UI at your API URL |
| `ADMIN_API_KEY` | Strongly recommended in prod | You generate | Protects `/api/ingest` |

Optional later upgrades (not required now):
- Cohere / Voyage / OpenAI embeddings (paid, faster hosted)
- Managed GPU for reranker
- Auth0 / Clerk for multi-user login

## Architecture

```
PDF corpus (data/documents + document_registry.json)
  → parse (PyMuPDF) → chunk (~900 chars) → BGE embed → Qdrant

User (Streamlit)
  → SSE POST /api/query/stream
  → dense retrieve (over-fetch) → cross-encoder rerank → grounding gate
  → Groq LLaMA 3.3 70B (regulatory | general | not_found)
  → streamed answer + source cards
```

## Answer modes

| Mode | Behavior |
|------|----------|
| `auto` (default) | Use regulatory citations when retrieval is confident; otherwise general finance |
| `regulatory` | Citations only; returns not-found if corpus is weak |
| `general` | Skip regulatory grounding; careful finance knowledge |

Grounding gate (defaults):
- `GROUNDED_MIN_SCORE=0.45` top dense score, **or**
- ≥2 hits at `SCORE_THRESHOLD=0.38`

## Accuracy / speed levers

| Lever | Default | Effect |
|-------|---------|--------|
| `ENABLE_RERANK` | true | Better citation precision; +latency on first load |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 900 / 120 | More context per chunk |
| `MAX_RETRIEVAL_CHUNKS` | 6 | Context budget |
| `RETRIEVAL_CANDIDATE_MULTIPLIER` | 4 | Retrieve 4× then rerank down |
| API warmup | on boot | Loads embedder (+ reranker) so first query is fast |

**Important:** After changing chunk size or embedding format, re-run:

```powershell
.\venv\Scripts\Activate.ps1
python -m ingestion.run_ingestion
```

Ingest is idempotent (deletes prior vectors for the same `filename` before upsert).

## Local development (Windows)

```powershell
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # fill keys

python -m ingestion.run_ingestion

# terminal 1
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# terminal 2
streamlit run frontend/app.py
```

Use **Python 3.11–3.13**. Avoid 3.14 for this stack.

## Deploy

### 1) API on Render (Docker)

1. Push repo to GitHub
2. Create a Render Web Service from `Dockerfile` (or use `render.yaml`)
3. Set secrets: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `ADMIN_API_KEY`
4. Set `APP_ENV=production`, `CORS_ORIGINS=https://your-app.streamlit.app`
5. Choose a plan with ≥2GB RAM (embeddings + optional reranker)
6. Health check: `/api/health`

### 2) UI on Streamlit Cloud

1. Deploy `frontend/app.py`
2. Add secret / env:
   - `COMPLIANCEIQ_API_URL=https://your-api.onrender.com/api`
3. Ensure Render CORS allows the Streamlit origin

### 3) Ingest in production

Either:
- Run ingestion locally against the same Qdrant Cloud collection, or
- `POST /api/ingest` with header `X-Admin-Key: <ADMIN_API_KEY>` (PDF must exist on the server filesystem — usually prefer local ingest into Qdrant Cloud)

## Security checklist

- [ ] Never commit `.env`
- [ ] Set `ADMIN_API_KEY` in production
- [ ] Restrict `CORS_ORIGINS` to your Streamlit URL
- [ ] Keep Qdrant API key private
- [ ] Treat answers as assistive — not legal advice

## Testing

```powershell
pytest -q
python -m evaluation.ragas_eval
```

Live Qdrant tests run only when `QDRANT_URL` / `QDRANT_API_KEY` are present.

## API surface

| Method | Path | Notes |
|--------|------|------|
| GET | `/` | Service metadata |
| GET | `/api/health` | Orchestrator health |
| GET | `/api/documents` | Unique docs in collection |
| POST | `/api/query` | Full JSON answer (`mode`, `latency_ms`) |
| POST | `/api/query/stream` | SSE: meta → token* → usage → `[DONE]` |
| POST | `/api/ingest` | Admin ingest (`X-Admin-Key`) |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `_cffi_backend` / broken native wheels | Recreate venv with Python 3.13 |
| API offline in UI | Start uvicorn; check `COMPLIANCEIQ_API_URL` |
| Weak / empty regulatory answers | Re-ingest; lower scope filter; try Auto mode |
| Slow first request | Wait for warmup logs; keep reranker enabled after warm |
| Duplicate vectors | Re-ingest (idempotent delete-by-filename is enabled) |
