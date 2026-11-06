# ComplianceIQ API Reference (v1)

Base URL: `http://localhost:8000` · Interactive docs: `/docs` (Swagger), `/redoc`.
Every v1 endpoint lives under `/api/v1`. The legacy `/api/*` routes used by the
Streamlit UI are listed at the end.

## Authentication

The API is designed to sit behind a trusted backend (e.g. the Next.js server), not
to be called from browsers directly.

| Header | Required | Purpose |
|---|---|---|
| `X-API-Key` | All `/api/v1/*` except `health` and `ready` | One of the comma-separated `API_KEYS`. If `API_KEYS` is empty the API is open in development and returns `503 auth_not_configured` in production. |
| `X-User-Id` | Optional | End-user id forwarded by the backend. Scopes conversations and feedback. Pattern `[A-Za-z0-9_.@:+-]{1,128}`; defaults to `anonymous`. |
| `X-Admin-Key` | `/api/v1/admin/*`, legacy `/api/ingest` | Must equal `ADMIN_API_KEY`. |

Every response carries `X-Request-ID` (send your own to correlate logs) and `X-Response-Time-ms`.

## Rate limits

`POST /chat`, `/chat/stream`, `/search` and legacy `/query*` share a sliding window
of `RATE_LIMIT_PER_MINUTE` (default 30) per API key + user. Exceeding it returns
`429 rate_limited` with `Retry-After`. The limiter is in-memory: use one instance
or put a Redis limiter in front when scaling out.

The upstream LLM (Groq free tier) has its own limit of about 8K tokens/minute per
model. When every model is exhausted, chat returns `503 llm_unavailable` (or an SSE
`error` event with `code: "rate_limited"`).

## Errors

All errors use one envelope:

```json
{
  "error": {
    "code": "conversation_not_found",
    "message": "Conversation not found.",
    "request_id": "7f0c…",
    "details": null
  },
  "detail": "Conversation not found."
}
```

| Status | Codes |
|---|---|
| 400 | `bad_request`, `invalid_user_id`, `invalid_page`, `empty_file` |
| 401 | `unauthorized` |
| 404 | `conversation_not_found`, `message_not_found`, `feedback_not_found`, `document_not_found`, `file_not_found`, `job_not_found`, `not_found` |
| 409 | `document_exists`, `job_running` |
| 413 | `file_too_large` |
| 415 | `invalid_file` |
| 422 | `validation_error` — `details: [{field, message}]` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 503 | `llm_unavailable`, `auth_not_configured`, `admin_disabled`, `index_unavailable` |

## Endpoints

| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET | `/api/v1/health` | – | `{status, version}` (liveness, public) |
| GET | `/api/v1/ready` | – | `{status: ready\|degraded, checks:{qdrant,database,models,llm}}`, 503 when degraded (public) |
| GET | `/api/v1/meta` | – | version, categories, answer modes, limits, feature flags, models |
| GET | `/api/v1/suggestions` | `category`, `limit` | `{category, suggestions[]}` |
| POST | `/api/v1/chat` | `ChatRequest` | `ChatResponse` |
| POST | `/api/v1/chat/stream` | `ChatRequest` | `text/event-stream` (see below) |
| PUT | `/api/v1/messages/{id}/feedback` | `{rating: 1\|-1, reasons?, comment?}` | `FeedbackResponse` |
| DELETE | `/api/v1/messages/{id}/feedback` | – | 204 |
| GET | `/api/v1/conversations` | `limit`, `offset`, `q`, `archived` | `{items, total, limit, offset}` |
| POST | `/api/v1/conversations` | `{title?, category, answer_mode}` | `Conversation` (201) |
| GET | `/api/v1/conversations/{id}` | – | `Conversation` + `messages[]` |
| PATCH | `/api/v1/conversations/{id}` | `{title?, pinned?, archived?, category?, answer_mode?}` | `Conversation` |
| DELETE | `/api/v1/conversations/{id}` | – | 204 |
| DELETE | `/api/v1/conversations` | – | `{deleted: n}` (all of this user's) |
| POST | `/api/v1/search` | `{query, category, top_k≤20, rerank}` | `{query, search_query, grounded, gate_score, results: Source[], timings}` |
| GET | `/api/v1/documents` | `category` | `DocumentSummary[]` |
| GET | `/api/v1/documents/{doc_id}` | – | `DocumentSummary` |
| GET | `/api/v1/documents/{doc_id}/outline` | – | `{doc_id, name, sections: [{section, page_number, passages}]}` |
| GET | `/api/v1/documents/{doc_id}/pages/{n}` | – | `{doc_id, name, page_number, total_pages, passages: [{chunk_id, seq, section, text}]}` |
| GET | `/api/v1/documents/{doc_id}/file` | – | The PDF (`application/pdf`). Add `#page=n` client-side. |
| POST | `/api/v1/admin/documents` | multipart: `file`, `name`, `category`, `circular_id?`, `subcategory?`, `date?` (YYYY-MM-DD), `issuer?`, `url?`, `replace?` | 202 `{document, job}` |
| PATCH | `/api/v1/admin/documents/{doc_id}` | `DocumentMetadataUpdate` | `{document, job}` (re-indexes so citations update) |
| DELETE | `/api/v1/admin/documents/{doc_id}` | `delete_file` | `{deleted, doc_id, file_deleted}` |
| POST | `/api/v1/admin/documents/{doc_id}/reindex` | – | 202 `IngestJob` |
| POST | `/api/v1/admin/reindex` | – | 202 `{jobs: IngestJob[]}` |
| GET | `/api/v1/admin/jobs` | `limit` | `IngestJob[]` |
| GET | `/api/v1/admin/jobs/{job_id}` | – | `IngestJob` — poll until `succeeded`/`failed` |
| GET | `/api/v1/admin/stats` | `days` (1–90) | `{usage, index, documents}` |
| POST | `/api/v1/admin/cache/clear` | – | 204 |

### ChatRequest

```json
{
  "question": "How often must KYC be updated for high-risk customers?",
  "conversation_id": null,
  "category": "ALL",
  "answer_mode": "auto",
  "top_k": 6,
  "history": null,
  "verify": null,
  "save": true
}
```

| Field | Notes |
|---|---|
| `question` | 3–2000 chars |
| `conversation_id` | Continue a saved conversation; history is loaded server-side |
| `category` | `ALL` · `RBI` · `SEBI` · `AA` |
| `answer_mode` | `auto` (cited when grounded, else general) · `regulatory` (cited or not-found) · `general` (no retrieval) |
| `top_k` | 1–10 passages, default 6 |
| `history` | Stateless clients only: `[{question, answer}]`, max 10. Ignored with `conversation_id`. |
| `verify` | Override verification (default on) |
| `save` | `false` → nothing persisted, `conversation_id` in the response is `null` |

### ChatResponse

```json
{
  "conversation_id": "0b6c2f0e-6a8e-4c1b-9a51-2f1f2f6c8d11",
  "message_id": "5d0e…",
  "user_message_id": "a41c…",
  "answer": "High-risk customers must update KYC at least once every two years [1]. …",
  "mode": "regulatory",
  "grounded": true,
  "gate_score": 0.998,
  "confidence": "high",
  "sources": [
    {
      "id": 1,
      "chunk_id": "…",
      "doc_id": "rbi-kyc-master-direction-2016",
      "doc_name": "RBI Master Direction on KYC 2016",
      "circular_id": "RBI/DBR.AML.BC.No.81/14.01.001/2015-16",
      "category": "RBI",
      "section": "Chapter VI Customer Due Diligence › 38. Periodic Updation",
      "page_number": 31,
      "date": "2016-02-25",
      "source_url": "https://…",
      "filename": "RBI_KYC_Master_Direction_2016.pdf",
      "snippet": "first 300 chars…",
      "text": "full passage",
      "relevance_score": 0.998,
      "citation": "RBI Master Direction on KYC 2016 | RBI/… | Chapter VI … | Page 31"
    }
  ],
  "verification": {
    "status": "verified",
    "score": 1.0,
    "method": "rules+llm",
    "claims_checked": 4,
    "supported": 4,
    "unsupported_claims": [],
    "uncited_claims": [],
    "invalid_citations": [],
    "unsupported_numbers": [],
    "citation_issues": []
  },
  "revised": false,
  "standalone_question": "How often must KYC be updated for high-risk customers?",
  "model": "openai/gpt-oss-120b",
  "latency_ms": 4090,
  "timings": {"search_ms": 310, "rerank_ms": 1800, "total_ms": 2150, "generation_ms": 1500, "verification_ms": 480}
}
```

`[n]` in `answer` refers to `sources[n-1].id == n`. `mode` is `regulatory`,
`general` or `not_found`. `confidence` is `null` for `not_found`.

## Streaming: `POST /api/v1/chat/stream`

Server-Sent Events. Each frame:

```
event: <type>
data: {"type": "<type>", …}
```

| Event | Payload | Client action |
|---|---|---|
| `conversation` | `{conversation_id, user_message_id}` | First frame when `save` is true. Update the URL / sidebar. |
| `status` | `{stage, message}` with stage `understanding` · `searching` · `thinking` · `writing` · `verifying` · `revising` | Show progress text. |
| `retrieval` | `{mode, grounded, gate_score, standalone_question, sources, timings}` | Render the sources panel before tokens arrive. |
| `token` | `{content}` | Append to the answer. |
| `revision` | `{answer, mode, sources?}` | **Replace** the streamed answer (normalised text, repaired answer, or refusal). |
| `verification` | `Verification` + `final: bool` | `final: false` precedes a repair; show the badge on `final: true`. |
| `done` | `{message_id, mode, answer, confidence, model, latency_ms}` | Authoritative final answer. Enable feedback with `message_id`. |
| `error` | `{code, message}` | `rate_limited`, `llm_error`, `internal_error`. The stream ends. |

Typical order: `conversation → status(searching) → retrieval → status(thinking) →
status(writing) → token* → [revision] → status(verifying) → verification → done`.
For a `not_found` answer: `retrieval → token → done` with no LLM call.

The exchange is persisted even if the client disconnects mid-stream.

## Examples

```bash
KEY=local-dev-key

# Ask (non-streaming)
curl -s http://localhost:8000/api/v1/chat \
  -H "X-API-Key: $KEY" -H "X-User-Id: user-42" -H "Content-Type: application/json" \
  -d '{"question":"What must a Key Fact Statement contain for digital loans?","category":"RBI"}'

# Stream (-N disables curl buffering)
curl -N http://localhost:8000/api/v1/chat/stream \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"question":"What are the consent requirements under the AA framework?"}'

# Follow-up in the same conversation
curl -s http://localhost:8000/api/v1/chat \
  -H "X-API-Key: $KEY" -H "X-User-Id: user-42" -H "Content-Type: application/json" \
  -d '{"question":"And for low risk customers?","conversation_id":"<id from the first answer>"}'

# Feedback
curl -s -X PUT http://localhost:8000/api/v1/messages/<message_id>/feedback \
  -H "X-API-Key: $KEY" -H "X-User-Id: user-42" -H "Content-Type: application/json" \
  -d '{"rating":-1,"reasons":["wrong_citation"],"comment":"Page 31 is about CDD"}'

# Upload a PDF (admin) and poll the job
curl -s http://localhost:8000/api/v1/admin/documents \
  -H "X-API-Key: $KEY" -H "X-Admin-Key: $ADMIN" \
  -F file=@RBI_Circular.pdf -F name="RBI Circular on X" -F category=RBI -F date=2025-04-01
curl -s http://localhost:8000/api/v1/admin/jobs/<job_id> -H "X-API-Key: $KEY" -H "X-Admin-Key: $ADMIN"
```

PowerShell users: use `curl.exe` and `--data-binary "@body.json"` to avoid quoting issues.

## Legacy routes (Streamlit)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/query` | `X-API-Key` | `{question, category, top_k, answer_mode, history}` → answer, sources, mode, confidence, verification |
| POST | `/api/query/stream` | `X-API-Key` | `data:` frames: `status`, `meta` (sources, mode), `token`, `revision`, `verification`, `usage`, then `data: [DONE]` |
| POST | `/api/ingest` | `X-API-Key` + `X-Admin-Key` | `{filename}` of a registered PDF, synchronous |
| GET | `/api/documents` | public | Documents in the index |
| GET | `/api/health` | public | Qdrant status and vector count |

## Smoke test

```powershell
python scripts/smoke_test.py --base http://localhost:8000 --api-key <key> --admin-key <admin-key>
```

Runs 12 live checks (readiness, grounded answer, follow-up rewrite, refusal,
documents, pages, outline, search, feedback, conversations, admin stats).
