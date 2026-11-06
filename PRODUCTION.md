# ComplianceIQ — Production Guide

Deployment, configuration, security and operations. How the RAG pipeline works is
in [docs/RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md); endpoints are in
[docs/API.md](docs/API.md).

## Accounts and keys

| Item | Required | Where | Notes |
|---|---|---|---|
| Groq API key | Yes | [console.groq.com](https://console.groq.com) | Free tier: ~8K tokens/min per model |
| Qdrant Cloud cluster | Yes | [cloud.qdrant.io](https://cloud.qdrant.io) | Free 1 GB cluster holds the current corpus easily |
| `API_KEYS` | Yes in production | You generate | Shared with the Next.js server / Streamlit |
| `ADMIN_API_KEY` | For uploads / re-index | You generate | Admin endpoints return 503 in production without it |
| Render (or any Docker host) | For the API | [render.com](https://render.com) | ≥ 2 GB RAM (torch + 3 local models) |
| Postgres | Optional | Neon, Supabase, Render | Instead of SQLite when running several instances |

Generate keys with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Configuration

All settings come from environment variables (or `.env`); see `.env.example` for
the full list with defaults. The ones that matter in production:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` (enforces API keys) |
| `API_KEYS` | comma-separated client keys |
| `ADMIN_API_KEY` | admin key |
| `CORS_ORIGINS` | your UI origins, e.g. `https://app.example.com` — only needed if a browser calls the API directly |
| `DATABASE_URL` | `sqlite:////var/data/complianceiq.db` on a persistent disk, or `postgresql://…` |
| `QDRANT_COLLECTION` | `regulations_v2` |
| `GROQ_MODEL` / `GROQ_FAST_MODEL` / `GROQ_FALLBACK_MODELS` | see below |

### Groq models

Groq retires models periodically; a retired model returns 404 and the client moves to
the next fallback automatically. To see what your key can use:

```powershell
python -m scripts.check_llm
```

Current defaults: answers `openai/gpt-oss-120b`, rewrite/verification `qwen/qwen3.8-27b`,
fallbacks `openai/gpt-oss-20b,qwen/qwen3.8-27b`. Each model has its own per-minute
token budget, so keep the answer model and the fast model different.

## Deploy

### API on Render (Docker)

1. Push the repo; create a Web Service from `render.yaml` (Blueprint) or the `Dockerfile`.
2. Set secrets: `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `API_KEYS`, `ADMIN_API_KEY`, `CORS_ORIGINS`.
3. `render.yaml` mounts a 1 GB disk at `/var/data` for SQLite. Use Postgres instead if you
   run more than one instance. Note that "one answer per conversation", stop, and the
   `streaming` flag are tracked in process memory: with several instances, pin each
   user to one instance (sticky sessions), or stop won't reach the instance generating
   the answer.
4. Health check: `/api/v1/health` (liveness). `/api/v1/ready` checks Qdrant, database,
   models and the LLM key — use it for alerts, not restarts.

The Docker image installs CPU-only torch and bakes in the embedding, BM25 and reranker
models, so cold starts don't download anything. Startup warm-up takes ~30–60 s on small
instances; the first request after that is fast.

### UI

- **Streamlit Cloud**: entry point `frontend/app.py` (dependencies in `frontend/requirements.txt`).
  Set `COMPLIANCEIQ_API_URL=https://<api>/api` and `COMPLIANCEIQ_API_KEY=<one of API_KEYS>`.
- **Next.js**: follow [docs/FRONTEND_NEXTJS.md](docs/FRONTEND_NEXTJS.md). The API key stays
  on the Next.js server (BFF); browsers never see it.

## Documents and ingestion

| Task | How |
|---|---|
| Initial load / full rebuild | `python -m ingestion.run_ingestion --recreate` (locally, against the production Qdrant) |
| One category / one file | `--category RBI` · `--file RBI_KYC_Master_Direction_2016.pdf` |
| Add a PDF in production | `POST /api/v1/admin/documents` (multipart) → poll `GET /api/v1/admin/jobs/{id}` |
| Fix metadata | `PATCH /api/v1/admin/documents/{doc_id}` (re-indexes automatically) |
| Remove | `DELETE /api/v1/admin/documents/{doc_id}?delete_file=true` |

Ingestion is idempotent: chunk IDs are derived from filename + position, and a
document's old vectors are deleted before upsert.

Uploaded PDFs are stored in `data/documents/` on the API host. On Render this is
ephemeral unless you move `data/` to the persistent disk; the vectors in Qdrant
survive either way, but re-index needs the file.

**After changing** `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBEDDING_MODEL` or the cleaning code,
rebuild with `--recreate`. **After changing** `RERANKER_MODEL`, re-calibrate
`RERANK_MIN_SCORE` with `python -m evaluation.run_eval retrieval`.

## Security checklist

- [ ] `.env`, PDFs and `data/*.db` are never committed (all gitignored)
- [ ] `APP_ENV=production` with `API_KEYS` and `ADMIN_API_KEY` set
- [ ] API keys only on servers (Next.js BFF / Streamlit secrets), never in browser code
- [ ] `CORS_ORIGINS` restricted, or unset if only server-to-server
- [ ] Qdrant and Groq keys rotated if ever exposed
- [ ] Answers are assistive, not legal advice

## Operations

| Signal | Where |
|---|---|
| Per-request logs with `request_id` | stdout (loguru); `X-Request-ID` response header |
| Usage, latency, verification and feedback stats | `GET /api/v1/admin/stats?days=7` |
| Every question, mode, gate score, verification, model, timings | `query_logs` table |
| Thumbs-down reasons | `feedback` table — review weekly; add failing questions to `evaluation/test_questions.json` |

Rate limiting is in-memory per instance (`RATE_LIMIT_PER_MINUTE`, default 30/user).
For multiple instances, put a shared limiter (Redis, API gateway) in front.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `model_not_found` / every answer errors | Model retired. Run `python -m scripts.check_llm`, update `GROQ_MODEL` / fallbacks. |
| `503 llm_unavailable`, `rate_limited` events | Groq per-minute token limit. Wait a minute, lower traffic, or use a paid tier. |
| `401 unauthorized` from the UI | `COMPLIANCEIQ_API_KEY` doesn't match `API_KEYS`. |
| `503 auth_not_configured` | `APP_ENV=production` without `API_KEYS`. |
| Everything is "not found" | Collection empty or wrong `QDRANT_COLLECTION`; check `/api/v1/ready` and re-ingest. |
| Answers marked "partially verified" often | Check `verification.unsupported_claims` in `query_logs`; usually missing context → raise `MAX_RETRIEVAL_CHUNKS` or fix the source PDF. |
| `_cffi_backend` / broken native wheels | Recreate the venv with Python 3.13. |
| Slow first request | Models are still warming; wait for "API ready" in the logs. |
| Streams arrive all at once / cut off after ~60 s | A proxy is buffering or timing out. Disable buffering (`X-Accel-Buffering: no` is sent; nginx `proxy_buffering off`), don't compress `text/event-stream`, raise idle timeouts above `SSE_HEARTBEAT_SECONDS`. |
| `409 conversation_busy` that never clears | An answer is still running (check `streaming` on the conversation). `POST /conversations/{id}/stop`; a restart also clears it. |
| Messages with status `stopped` | The client disconnected or pressed Stop; the partial answer was saved. Retry with `regenerate`. |
