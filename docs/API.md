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

`POST /chat`, `/chat/stream`, `/messages/{id}/regenerate`, `/messages/{id}/edit`,
`/search` and legacy `/query*` share a sliding window of `RATE_LIMIT_PER_MINUTE`
(default 30) per API key + user. Exceeding it returns `429 rate_limited` with
`Retry-After`. The limiter is in-memory: use one instance or put a Redis limiter in
front when scaling out.

The upstream LLM (Groq free tier) has its own limit of about 8K tokens/minute per
model. When a model is rate limited the next fallback model is used (the stream
shows "switching to a backup model…"). When every model is exhausted, chat returns
`503 llm_unavailable` (or an SSE `error` event with `code: "rate_limited"`).

## Conversation rules

- **One answer at a time per conversation.** While an answer is being generated,
  another chat/regenerate/edit in the same conversation returns `409
  conversation_busy`. `GET /conversations/{id}` reports `streaming: true` meanwhile.
  Stop it with `POST /conversations/{id}/stop` or wait.
- **Answers are saved by the server, not the client.** If the client disconnects
  (tab closed, network drop, fetch aborted) generation stops and the partial answer
  is saved with `status: "stopped"`. A failure saves the partial answer with
  `status: "error"`. Both can be retried with `regenerate`.
- **Sticky settings.** The `category` and `answer_mode` of each request are saved on
  the conversation, so the next turn (and regenerate) reuse them.
- **Titles.** A new conversation is titled from the first question, then replaced
  by a short AI title after the first answer (`title` event / field). A title the
  user set with `PATCH` is never overwritten. Editing the first question re-titles
  only if the title is still the automatic one.
- The run registry is in-process: run a single API instance, or pin a conversation
  to one instance (sticky sessions).

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
| 400 | `bad_request`, `invalid_user_id`, `invalid_page`, `empty_file`, `invalid_message` (regenerate needs an assistant message, edit a user message) |
| 401 | `unauthorized` |
| 404 | `conversation_not_found`, `message_not_found`, `feedback_not_found`, `document_not_found`, `file_not_found`, `job_not_found`, `not_found` |
| 409 | `conversation_busy`, `document_exists`, `job_running` |
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
| POST | `/api/v1/messages/{id}/regenerate` | `RegenerateRequest` (optional) | SSE. `id` = assistant message. Replaces it and removes every later message. Also "retry" for `error`/`stopped` answers. |
| POST | `/api/v1/messages/{id}/edit` | `EditRequest` | SSE. `id` = user message. Replaces the question, removes every later message, answers it. |
| GET | `/api/v1/messages/{id}` | – | `Message` (sources, verification, follow-ups, your feedback) |
| PUT | `/api/v1/messages/{id}/feedback` | `{rating: 1\|-1, reasons?, comment?}` | `FeedbackResponse` |
| DELETE | `/api/v1/messages/{id}/feedback` | – | 204 |
| GET | `/api/v1/conversations` | `limit`, `offset`, `q`, `archived` | `{items, total, limit, offset}` |
| POST | `/api/v1/conversations` | `{title?, category, answer_mode}` | `Conversation` (201) |
| GET | `/api/v1/conversations/{id}` | – | `Conversation` + `messages[]` + `streaming` |
| PATCH | `/api/v1/conversations/{id}` | `{title?, pinned?, archived?, category?, answer_mode?}` | `Conversation` |
| POST | `/api/v1/conversations/{id}/stop` | – | `{conversation_id, stopped}`; `stopped: false` when nothing was running |
| GET | `/api/v1/conversations/{id}/export` | `format=markdown\|json` | File download (`Content-Disposition: attachment`) with answers, verification and full citations |
| DELETE | `/api/v1/conversations/{id}` | – | 204 (stops a running answer first) |
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
  "save": true,
  "followups": true
}
```

| Field | Notes |
|---|---|
| `question` | 3–2000 chars (trimmed) |
| `conversation_id` | Continue a saved conversation; history is loaded server-side |
| `category` | `ALL` · `RBI` · `SEBI` · `AA` |
| `answer_mode` | `auto` (cited when grounded, else general) · `regulatory` (cited or not-found) · `general` (no retrieval) |
| `top_k` | 1–10 passages, default 6 |
| `history` | Stateless clients only: `[{question, answer}]`, max 10. Ignored with `conversation_id`. |
| `verify` | Override verification (default on) |
| `save` | `false` → nothing persisted, `conversation_id` in the response is `null` |
| `followups` | Suggest up to 3 next questions after the answer (default `true`) |

### RegenerateRequest / EditRequest

```json
{ "category": null, "answer_mode": null, "top_k": null, "verify": null, "followups": true }
```

Every field is optional; omitted `category`/`answer_mode` reuse the conversation's
settings, given ones are saved on the conversation. `EditRequest` adds the required
`"question"` (3–2000 chars). Both stream exactly like `/chat/stream`.

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
  "timings": {"search_ms": 310, "rerank_ms": 1800, "total_ms": 2150, "generation_ms": 1500, "verification_ms": 480},
  "followups": ["What triggers an immediate KYC update?", "How are customer risk categories determined?"],
  "title": "Periodic KYC Update Timelines"
}
```

`[n]` in `answer` refers to `sources[n-1].id == n`. `mode` is `regulatory`,
`general` or `not_found`. `confidence` is `null` for `not_found`. `title` is set
only when this exchange changed the conversation title. `followups` is empty when
disabled; for `not_found` answers it holds starter questions that the documents do cover.

In `auto` mode, if the documents look relevant but the model finds they don't
actually answer the question, the API falls back to a general-knowledge answer
(`mode: "general"`, no sources, `confidence: "low"`) instead of a refusal. In
`regulatory` mode the same case returns `not_found`.

### Message

```json
{
  "id": "…", "conversation_id": "…", "role": "assistant",
  "content": "…", "status": "complete",
  "mode": "regulatory", "followups": ["…"], "sources": [/* Source */], "verification": {/* … */},
  "confidence": "high", "revised": false, "standalone_question": "…",
  "model": "openai/gpt-oss-120b", "latency_ms": 4090, "created_at": "2026-11-06T10:12:03Z",
  "feedback": {"rating": 1, "reasons": [], "comment": null}
}
```

`status`: `complete` · `stopped` (cut short by the user or a disconnect; `content` is
the partial answer) · `error` (generation failed; `content` may be partial). User
messages are always `complete`.

## Streaming: `POST /api/v1/chat/stream`

`/messages/{id}/regenerate` and `/messages/{id}/edit` use the same protocol.
Validation, `404` and `409 conversation_busy` errors are returned as normal JSON
responses **before** the stream starts, so check `response.ok` first.

Server-Sent Events. Each frame:

```
event: <type>
data: {"type": "<type>", …}
```

Lines starting with `:` (`: ping`) are heartbeats, sent every
`SSE_HEARTBEAT_SECONDS` (default 10, see `/meta` `limits.sse_heartbeat_seconds`) while
the server is busy without output. Ignore them. They keep proxies from closing idle
connections and let the server notice a disconnected client.

| Event | Payload | Client action |
|---|---|---|
| `conversation` | `{conversation_id, user_message_id}` | First frame for saved chats. Update the URL / sidebar, attach the id to the user bubble. |
| `status` | `{stage, message}` with stage `understanding` · `searching` · `thinking` · `writing` · `verifying` · `revising` | Show `message` as progress text. |
| `retrieval` | `{mode, grounded, gate_score, standalone_question, sources, timings}` | Render the sources before tokens arrive. |
| `token` | `{content}` | Append to the answer. |
| `revision` | `{answer, mode, reason, sources?}` | **Replace** the answer text with `answer`; later tokens append to it. If `sources` is present, replace the sources. |
| `verification` | `Verification` + `final: bool` | `final: false` precedes a repair; show the badge on `final: true`. |
| `followups` | `{followups: string[]}` | Show suggested next questions as chips. |
| `title` | `{conversation_id, title}` | Update the conversation title in the sidebar/header. |
| `error` | `{code, message}` | `rate_limited`, `llm_error`, `internal_error`. No more content follows; `done` still arrives. |
| `done` | `{status, message_id, conversation_id, mode, answer, confidence, model, latency_ms}` | **Always the last frame.** `status`: `complete` · `stopped` · `error`. `answer` is the saved text. Use `message_id` for feedback, regenerate and copy. |

`revision.reason`:

| `reason` | Meaning | UI |
|---|---|---|
| `format` | Typography cleanup of the streamed text | Swap silently |
| `repair` | Fact-check found unsupported claims; corrected answer | Crossfade + "Refined after fact-check" |
| `not_found` | Model said the documents don't cover it (`regulatory` mode) | Show the not-found card, drop sources |
| `general_fallback` | Same, in `auto` mode: `answer` is `""`, `sources` `[]`, and a general-knowledge answer streams next | Clear the text, switch to the general-knowledge banner |

Typical order:

```
conversation → status(searching) → retrieval → status(thinking) → status(writing) → token*
  → [revision(format)] → status(verifying) → [verification(final:false) → status(revising) → revision(repair)]
  → verification(final:true) → followups → [title] → done(complete)
```

- `not_found` without an LLM call: `retrieval → token (the refusal text) → [followups] → done`.
- Follow-up questions add `status(understanding)` before `searching`.
- Model fallback adds `status(thinking, "The primary model is busy, switching to a backup model…")`.
- Stopped: the stream ends with `done(status: "stopped")` holding the partial answer; no `followups`/`title`.
- Failure: `error → done(status: "error")`.

## Stop, regenerate, edit, export

```bash
# Stop the running answer (the open stream ends with done.status = "stopped")
curl -s -X POST http://localhost:8000/api/v1/conversations/<id>/stop -H "X-API-Key: $KEY" -H "X-User-Id: user-42"

# Regenerate / retry an assistant answer (SSE)
curl -N -X POST http://localhost:8000/api/v1/messages/<assistant_message_id>/regenerate \
  -H "X-API-Key: $KEY" -H "X-User-Id: user-42" -H "Content-Type: application/json" -d '{"answer_mode":"regulatory"}'

# Edit a question and re-answer (SSE)
curl -N -X POST http://localhost:8000/api/v1/messages/<user_message_id>/edit \
  -H "X-API-Key: $KEY" -H "X-User-Id: user-42" -H "Content-Type: application/json" \
  -d '{"question":"What is the cooling-off period for digital loans?"}'

# Export
curl -s -OJ "http://localhost:8000/api/v1/conversations/<id>/export?format=markdown" -H "X-API-Key: $KEY" -H "X-User-Id: user-42"
```

Aborting the HTTP request has the same effect as `stop`: generation ends at the
next step (usually within a second; up to a few seconds while searching or
fact-checking) and the partial answer is saved as `stopped`.

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

Runs 19 live checks against real Qdrant and Groq: readiness, a grounded answer
(saved, with follow-ups and an AI title), follow-up rewrite, regenerate, stop
mid-answer, edit, export, out-of-scope refusal, auto-mode general fallback,
documents, pages, outline, search, feedback, conversations and admin stats.
