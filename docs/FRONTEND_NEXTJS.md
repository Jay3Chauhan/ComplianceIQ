# ComplianceIQ — Next.js Frontend Specification

This document is the build spec for the production web frontend. It covers architecture, design system, every screen and component, UX states, the complete backend contract (with TypeScript types), and reference code for the parts that are easy to get wrong (SSE streaming, citation rendering, the server-side proxy).

Backend reference: [`docs/API.md`](API.md). RAG internals: [`docs/RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md).

---

## 1. Product summary

ComplianceIQ answers questions about Indian financial regulation (RBI master directions, SEBI master circulars, the Account Aggregator framework) **only from loaded documents**, with inline citations, and tells the user when the documents don't cover a question.

**Primary users:** compliance officers, fintech founders and product managers, legal teams.

**What the UI must make obvious, at a glance, for every answer:**

1. **Where it came from:** inline `[n]` citations linked to the exact document, section and page.
2. **How trustworthy it is:** the verification status (every claim fact-checked against the sources) and a confidence level.
3. **What kind of answer it is:** a cited document answer, a general-knowledge answer (not from documents), or "not found".

Hallucination resistance is a product feature. The UI has to surface it, not hide it.

---

## 2. Architecture

```
Browser ──▶ Next.js (App Router)
              ├─ React Server Components (pages, initial data)
              ├─ Route Handlers  /app/api/**   ← "BFF" proxy, adds secrets
              └─ Auth (Auth.js / Clerk / Better Auth)
                        │  X-API-Key: <server secret>
                        │  X-User-Id: <session user id>
                        │  X-Request-ID: <uuid>
                        ▼
              FastAPI  /api/v1/**  (ComplianceIQ backend)
```

**Rules**

- The browser **never** calls FastAPI directly and never sees `X-API-Key` or `X-Admin-Key`. All calls go through Next.js route handlers (`/app/api/...`), which attach the headers server-side.
- `X-User-Id` comes from the authenticated session (e.g. `session.user.id`). The backend scopes conversations and feedback by it.
- Admin routes check the user's role in Next.js **and** attach `X-Admin-Key` only for admins.
- Streaming (`/api/v1/chat/stream`) is proxied by piping the upstream `ReadableStream` straight through (see §9.2).

### 2.1 Tech stack

| Concern | Choice |
|---|---|
| Framework | Next.js 15 (App Router), React 19, TypeScript (strict) |
| Styling | Tailwind CSS v4 + CSS variables, `shadcn/ui` (Radix primitives) |
| Server state | TanStack Query v5 |
| Client state | Zustand (only for the active stream and UI prefs) |
| Validation | Zod (parse every backend response in the BFF) |
| Markdown | `react-markdown` + `remark-gfm` (no raw HTML) |
| Icons | `lucide-react` |
| Toasts | `sonner` |
| Theming | `next-themes` (light / dark / system) |
| PDF viewer | Browser-native viewer in an `<iframe>` with `#page=N`, or `react-pdf` for in-app highlighting |
| Auth | Auth.js (or Clerk / Better Auth). Any provider that gives a stable user id |
| Tests | Vitest + React Testing Library, Playwright + MSW for E2E with mocked SSE |

### 2.2 Environment variables

```env
# server-only (never NEXT_PUBLIC_)
COMPLIANCEIQ_API_URL=https://complianceiq-api.onrender.com   # FastAPI base URL, no trailing slash
COMPLIANCEIQ_API_KEY=...        # one of the backend's API_KEYS
COMPLIANCEIQ_ADMIN_KEY=...      # backend ADMIN_API_KEY (admin features only)
AUTH_SECRET=...

# public
NEXT_PUBLIC_APP_NAME=ComplianceIQ
```

---

## 3. Information architecture

| Route | Purpose | Rendering |
|---|---|---|
| `/` | New chat: empty state with suggestions, composer | RSC shell + client chat |
| `/c/[conversationId]` | Existing conversation | RSC fetches conversation, client hydrates |
| `/search` | Passage search across documents (no LLM) | Client |
| `/documents` | Library: all documents, filters by regulator | RSC |
| `/documents/[docId]` | Document detail: metadata, outline, page passages, PDF | RSC + client viewer |
| `/admin` | Overview stats (usage, verification, feedback) | RSC (admin only) |
| `/admin/documents` | Upload, edit metadata, reindex, delete; job progress | Client (admin only) |
| `/settings` | Theme, default regulator, default answer mode, delete all history | Client |

Deep links:
- `/documents/[docId]?page=33&chunk=<chunk_id>` opens the page and highlights the cited passage.
- `/c/[id]#m-<messageId>` scrolls to a message.

---

## 4. Design system

### 4.1 Principles

- **Calm and legible.** This is a professional research tool. Use generous line-height, restrained color, and no decorative gradients behind text.
- **Evidence first.** Citations, sources and verification are first-class UI, never buried in a footer.
- **Honest states.** Never show a spinner without saying what is happening (see the stage labels in §6.2).

### 4.2 Tokens (CSS variables, Tailwind theme)

```css
:root {
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --muted: 210 40% 96%;
  --muted-foreground: 215 16% 47%;
  --border: 214 32% 91%;
  --primary: 222 70% 42%;          /* deep indigo-blue: brand, primary actions */
  --primary-foreground: 0 0% 100%;
  --ring: 222 70% 42%;

  /* regulator accents (badges, source card left border) */
  --rbi: 217 91% 45%;              /* blue   */
  --sebi: 25 95% 48%;              /* orange */
  --aa: 152 60% 36%;               /* green  */
  --general: 262 52% 50%;          /* violet: general-knowledge answers */

  /* trust states */
  --verified: 152 60% 36%;
  --partial: 38 92% 45%;
  --unverified: 0 72% 48%;
  --notfound: 215 16% 47%;

  --radius: 0.75rem;
}
.dark {
  --background: 224 32% 8%;
  --foreground: 210 40% 96%;
  --muted: 223 25% 14%;
  --muted-foreground: 215 20% 65%;
  --border: 223 20% 20%;
  --primary: 217 91% 65%;
  --primary-foreground: 224 32% 8%;
}
```

- **Typography:** Inter (UI, answers) at 15px/1.7 for answer text, and JetBrains Mono for circular IDs and the `[n]` chips. Headings use `font-semibold` with tight tracking.
- **Layout widths:** answer column `max-w-3xl`; sidebar 280px; sources panel 380px.
- **Motion:** 150–200ms ease-out for panels; token streaming has no animation beyond a blinking caret; respect `prefers-reduced-motion`.

### 4.3 Semantic badges

| Badge | When | Look |
|---|---|---|
| `RBI` / `SEBI` / `AA` | category of a source/document | pill, regulator accent at 12% bg, 100% text |
| `Cited from documents` | `mode = "regulatory"` | primary outline pill with `FileCheck` icon |
| `General knowledge` | `mode = "general"` | violet pill with `Sparkles` icon |
| `Not in documents` | `mode = "not_found"` | muted pill with `SearchX` icon |
| `Verified` | `verification.status = "verified"` | green, `ShieldCheck` |
| `Partially verified` | `"partially_verified"` | amber, `ShieldAlert` |
| `Unverified` | `"unverified"` | red, `ShieldX` |
| `High / Medium / Low confidence` | `confidence` | 3-segment meter + label |
| `Refined after fact-check` | `revised = true` | small amber text badge with `Wand2` |

---

## 5. Layout

```
┌──────────────┬────────────────────────────────────────┬─────────────────┐
│ Sidebar      │  Top bar: title · regulator · mode     │ Sources panel   │
│ + New chat   ├────────────────────────────────────────┤ (collapsible)   │
│ Search chats │                                        │ [1] KYC MD 2016 │
│ Pinned       │   Message list (max-w-3xl, centered)   │  Ch VI › 38 ... │
│ Today        │                                        │  p.33  ▸ open   │
│ Previous 7d  │                                        │ [2] ...         │
│ Older        │                                        │                 │
│ ─────────    │                                        │                 │
│ Library      ├────────────────────────────────────────┤                 │
│ Search       │  Composer (sticky bottom)              │                 │
│ Admin        │                                        │                 │
└──────────────┴────────────────────────────────────────┴─────────────────┘
```

- **≥1280px:** three panes. The sources panel opens automatically when an answer with sources arrives and can be pinned or closed.
- **768–1279px:** the sidebar collapses to icons; sources open as a right sheet.
- **<768px:** the sidebar becomes a drawer (hamburger menu), sources become a bottom sheet, and the composer stays fixed with a safe-area inset.

---

## 6. Chat experience

### 6.1 Composer

- An auto-growing textarea (1–8 rows) with a 2,000-character limit and a counter that appears after 1,600.
- **Controls row:**
  - **Regulator selector:** `All · RBI · SEBI · AA`, sourced from `GET /meta` categories.
  - **Answer mode selector:** `Auto · Documents only · General knowledge`, each with a one-line description from `/meta.answer_modes`.
  - **Send button.** While streaming it becomes a **Stop** button.
- **Keys:** `Enter` sends, `Shift+Enter` inserts a newline, `Esc` stops the stream, `↑` in an empty composer edits the last question.
- **Disabled while streaming.** Stop aborts the fetch (§9.3). The partial answer is kept and marked "Stopped".
- **Persistence:** regulator and mode are remembered per conversation (`PATCH /conversations/{id}`). New chats start from the defaults in `/settings`.

### 6.2 Streaming stages → UI

Drive a single **status line** above the streaming answer from `status` events. Never show two spinners.

| `stage` | Label (use the backend `message` if present) | Icon |
|---|---|---|
| `understanding` | Understanding your follow-up… | `MessageSquareText` (pulse) |
| `searching` | Searching regulatory documents… | `Search` (pulse) |
| `thinking` | Reading the sources… | `BookOpen` (pulse) |
| `writing` | Writing answer… | blinking caret at end of text |
| `verifying` | Checking every claim against the sources… | `ShieldQuestion` (pulse) |
| `revising` | Fixing unsupported statements… | `Wand2` (pulse) |
| *(done)* | status line disappears; badges render | — |

After the `retrieval` event, show **"Found N sources"** chips immediately, before any tokens arrive, so the user sees evidence first.

### 6.3 Assistant message anatomy

```
┌─────────────────────────────────────────────────────────────┐
│ [Cited from documents] [Verified ✓] [High confidence ▮▮▮]   │  ← header badges (after done)
│                                                             │
│ Periodic updation must be carried out at least once every   │
│ **two years** for high-risk customers [1] …                 │  ← markdown with citation chips
│                                                             │
│ • Medium risk: once every **eight years** [1]               │
│                                                             │
│ Sources: [1] KYC MD 2016 · p.33   [2] KYC MD 2016 · p.34    │  ← compact source row
│                                                             │
│ 👍 👎  ⧉ Copy  ↻ Regenerate  ⋯ (Show verification details)    │  ← action bar
└─────────────────────────────────────────────────────────────┘
```

- **Citation chips:** `[1]` renders as a small mono chip.
  - Hover or focus shows a **HoverCard** with the doc name, circular ID, section, page, a snippet, and an "Open page" button.
  - Clicking scrolls to and highlights the source in the Sources panel.
  - Chips that point to a non-existent source (shouldn't happen after verification) render struck-through and muted.
- **Verification details** open in a popover:
  - The status line, e.g. "8/8 claims supported", with the score as a percentage.
  - The method: "Rules + AI fact-check" or "Rules only".
  - If present, lists of unsupported claims (with reasons), figures not found in sources, and invalid citations.
  - If `revised`, a note: "The first draft contained unsupported statements and was corrected automatically."
- **General mode banner** (`mode = "general"`): a violet info strip above the text, stating: "This answer is from general knowledge, not from the loaded regulatory documents. Verify on the regulator's website." No source row.
- **Not-found state** (`mode = "not_found"`): a muted card with a `SearchX` icon and the backend text (markdown), plus three quick actions:
  - "Search all regulators" (re-asks with `category=ALL`)
  - "Ask in General knowledge mode" (re-asks with `answer_mode=general`)
  - "Browse documents"
- **Confidence meter:** 3 segments; high is all three, medium two, low one; `null` hides the meter.
- **Copy:** copies the answer markdown plus a "Sources" list (`[n] doc name, circular id, section, page`).
- **Regenerate:** re-sends the same question in the same conversation. The backend creates a new message pair; show the newest one.

### 6.4 Sources panel

- A list of `SourceCard`s, numbered to match the citations:
  - The header shows a regulator badge, the doc name (2-line clamp), and the circular ID in mono.
  - The meta line shows the section (1-line clamp, with a tooltip for the full text), the page, and the date.
  - The body is the snippet, with an "Expand" toggle that shows the full `text`.
  - The footer has a relevance bar (`relevance_score` is in 0–1), "Open page" (goes to `/documents/{doc_id}?page=N&chunk=...`), and "Official source ↗" (`source_url`, opens a new tab).
- Clicking `[n]` in the answer scrolls to card n and flashes a 1s ring.
- Panel header: "Sources (N)" plus a toggle between "This answer" and "All in conversation".

### 6.5 Conversation sidebar

- Groups: Pinned, Today, Previous 7 days, Previous 30 days, Older (by `updated_at`).
- Row actions on hover or via the `⋯` menu: Rename (inline edit), Pin/Unpin, Archive, Delete (with a confirm dialog).
- The search box calls `GET /conversations?q=` (debounced 250ms); the backend searches titles and message text.
- The list is paginated with `limit=30&offset=…` (infinite scroll).
- A new conversation appears at the top as soon as the `conversation` SSE event arrives. Its title comes from the first question, so update the cache optimistically.

### 6.6 Empty state (`/`)

- Logo, a one-line value proposition, and the regulator chips.
- Four suggestion cards from `GET /suggestions?category=<selected>&limit=4`. Clicking one sends it immediately.
- Footnote: "Answers cite loaded documents only. Not legal advice."

### 6.7 Feedback

- 👍 sends `PUT /messages/{id}/feedback {rating: 1}` immediately. Clicking it again removes the rating (`DELETE`).
- 👎 opens a small popover:
  - Reason checkboxes: Incorrect, Not supported by sources, Missing information, Wrong citation, Outdated, Unclear, Too long, Other.
  - An optional comment field and a Submit button.
- Show the existing rating from `message.feedback` when a conversation loads.

---

## 7. Other screens

### 7.1 Search (`/search`)

- A query box, a regulator filter, and a "Rerank (more precise)" toggle (on by default).
- Calls `POST /search` and renders results as `SourceCard`s with relevance bars.
- If `grounded = false`, show a warning: "No passage is a strong match — results may be loosely related."
- Each result has an "Ask about this" button that opens a new chat prefilled with: `"Explain: <section> (<doc name>, p.<page>)"`.

### 7.2 Library (`/documents`)

- A grid or table of documents from `GET /documents?category=`.
- Each row shows the regulator badge, name, circular ID, date, issuer, chunk count, `indexed` status, and links to "Open" and "Official source".
- Filters for regulator and a text filter (client-side).

### 7.3 Document detail (`/documents/[docId]`)

- The header shows the metadata plus Download PDF (`GET /documents/{id}/file`) and Official source buttons.
- **Left:** the outline from `GET /documents/{id}/outline`, as a list of sections with their first page; clicking one jumps to that page.
- **Center:** a tabbed view:
  - **Passages:** shows `GET /documents/{id}/pages/{n}` passages in reading order. The passage matching `?chunk=` is highlighted and scrolled into view. Pager: prev/next page, and a page input bounded by `total_pages`.
  - **PDF:** an `<iframe src="/api/documents/{id}/file#page=N">` that streams through the BFF.

### 7.4 Admin

- **Overview (`/admin`):** cards come from `GET /admin/stats?days=7|30`:
  - Total queries, plus a breakdown by mode (regulatory, general, not_found).
  - Grounded rate.
  - Verification breakdown (verified, partially verified, unverified) and the revised-answer count.
  - p50/p95 latency.
  - Feedback 👍/👎.
  - Index points.

  It also lists "Recent unanswered questions", which highlights coverage gaps for adding documents.
- **Documents (`/admin/documents`):**
  - **Upload dialog** (multipart `POST /admin/documents`):
    - Fields: file dropzone (PDF only, max `limits.max_upload_mb`), name, regulator, circular ID, subcategory, date, issuer, official URL.
    - A "Replace if exists" checkbox (handles 409).
  - **After upload:** show a job progress row. Poll `GET /admin/jobs/{id}` every 2s until `succeeded` or `failed`. Stages: parsing → chunking → embedding → done.
  - **Row actions:** Edit metadata (`PATCH`, which triggers a reindex job), Reindex, and Delete (confirm; "also delete PDF file" checkbox).
  - **Jobs table:** fed by `GET /admin/jobs`.

### 7.5 Settings

- Theme, default regulator, default answer mode, "Show verification details by default".
- **Danger zone:** "Delete all conversations" calls `DELETE /conversations` and requires typing a confirmation.

---

## 8. Backend contract

Base URL (server-side only): `${COMPLIANCEIQ_API_URL}/api/v1`.
Headers on every call: `X-API-Key`, `X-User-Id`, `X-Request-ID` (generate a UUID), and `Content-Type: application/json`.
Admin calls add `X-Admin-Key`.

### 8.1 TypeScript types

```ts
// lib/api/types.ts
export type Category = "ALL" | "RBI" | "SEBI" | "AA";
export type AnswerMode = "auto" | "regulatory" | "general";
export type ResponseMode = "regulatory" | "general" | "not_found";
export type Confidence = "high" | "medium" | "low" | null;
export type VerificationStatus = "verified" | "partially_verified" | "unverified" | "not_applicable";

export interface Source {
  id: number;                 // citation number used as [n]
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  circular_id: string;
  category: string;           // RBI | SEBI | AA | GENERAL
  section: string;            // e.g. "Chapter VI › 38. Periodic Updation" (may be "")
  page_number: number;
  date: string;               // YYYY-MM-DD or ""
  source_url: string;
  filename: string;
  snippet: string;            // ≤ 320 chars
  text: string;               // full passage
  relevance_score: number;    // 0..1 (reranker probability)
  citation: string;           // preformatted "Doc | Circular | Section | Page n"
}

export interface Verification {
  status: VerificationStatus;
  score: number;              // 0..1
  method: "rules" | "rules+llm" | "none";
  claims_checked: number;
  supported: number;
  unsupported_claims: { claim: string; reason: string }[];
  uncited_claims: string[];
  invalid_citations: number[];
  unsupported_numbers: string[];
  citation_issues: string[];
}

export interface ChatRequest {
  question: string;                 // 3..2000 chars
  conversation_id?: string | null;  // omit to start a new conversation
  category?: Category;              // default "ALL"
  answer_mode?: AnswerMode;         // default "auto"
  top_k?: number;                   // 1..10, default 6
  history?: { question: string; answer: string }[]; // only for save=false
  verify?: boolean;                 // default true
  save?: boolean;                   // default true
}

export interface ChatResponse {
  conversation_id: string | null;
  message_id: string | null;
  user_message_id: string | null;
  answer: string;                   // markdown with [n] citations
  mode: ResponseMode;
  grounded: boolean;
  gate_score: number;
  confidence: Confidence;
  sources: Source[];
  verification: Verification | null;
  revised: boolean;
  standalone_question: string;
  model: string | null;
  latency_ms: number;
  timings: Record<string, number>;
}

export interface Conversation {
  id: string; title: string; category: Category; answer_mode: AnswerMode;
  pinned: boolean; archived: boolean; message_count: number;
  created_at: string; updated_at: string;   // ISO 8601 UTC
}
export interface Message {
  id: string; conversation_id: string; role: "user" | "assistant";
  content: string; status: "complete" | "error";
  mode: ResponseMode | null; sources: Source[]; verification: Verification | null;
  confidence: Confidence; revised: boolean; standalone_question: string | null;
  model: string | null; latency_ms: number | null; created_at: string;
  feedback: { rating: 1 | -1; reasons: string[]; comment: string | null } | null;
}
export interface ConversationDetail extends Conversation { messages: Message[] }
export interface Paginated<T> { items: T[]; total: number; limit: number; offset: number }

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string; details?: unknown };
  detail: string;
}
```

### 8.2 SSE event union (`POST /chat/stream`)

Each frame looks like this:

```
event: <type>
data: {"type":"<type>", ...}

```

The `type` field is duplicated inside the JSON, so you can parse `data:` lines alone.

```ts
export type StreamEvent =
  | { type: "conversation"; conversation_id: string; user_message_id: string | null }
  | { type: "status"; stage: "understanding" | "searching" | "thinking" | "writing" | "verifying" | "revising"; message: string }
  | { type: "retrieval"; mode: ResponseMode; grounded: boolean; gate_score: number;
      standalone_question: string; sources: Source[]; timings: Record<string, number> }
  | { type: "token"; content: string }
  | ({ type: "verification"; final: boolean } & Verification)
  | { type: "revision"; answer: string; mode: ResponseMode; sources?: Source[] }
  | { type: "done"; message_id: string | null; conversation_id: string | null; mode: ResponseMode;
      answer: string; confidence: Confidence; model: string | null; latency_ms: number }
  | { type: "error"; code: "rate_limited" | "llm_error" | "internal_error"; message: string };
```

Ordering guarantees:

- `conversation` (only when saving) → `status(searching)` → `retrieval` → `status(thinking)` → `status(writing)` → `token`… → [`status(verifying)` → (`verification{final:false}` → `status(revising)` → `revision`)? → `verification{final:true}`] → `done`.
- For `not_found`, the sequence is `retrieval` → a single `token` holding the full refusal text → `done`.
- `revision.answer` **replaces** the streamed text entirely. Animate a crossfade and show "Refined after fact-check".
- `done.answer` is the canonical final text; always overwrite the local buffer with it.
- If `retrieval.mode` is `regulatory` and a later `revision.mode` is `not_found`, drop the sources and show the not-found card.
- `error` can occur at any time and ends the stream. The partial assistant message is saved server-side with `status: "error"`.

### 8.3 Endpoint table

| Method & path | Body / query | Returns | Notes |
|---|---|---|---|
| `GET /health` | — | `{status:"ok", version}` | no auth |
| `GET /ready` | — | `{status, checks}` (200 or 503) | no auth |
| `GET /meta` | — | categories, answer_modes, limits, features, models | cache 1h |
| `GET /suggestions` | `?category=&limit=` | `{category, suggestions: string[]}` | |
| `POST /chat` | `ChatRequest` | `ChatResponse` | 429/503 possible |
| `POST /chat/stream` | `ChatRequest` | SSE (`StreamEvent`) | 404 if conversation not yours |
| `GET /conversations` | `?limit=30&offset=0&q=&archived=false` | `Paginated<Conversation>` | pinned first, then `updated_at` desc |
| `POST /conversations` | `{title?, category?, answer_mode?}` | `Conversation` (201) | |
| `GET /conversations/{id}` | — | `ConversationDetail` | includes your feedback per message |
| `PATCH /conversations/{id}` | `{title?, pinned?, archived?, category?, answer_mode?}` | `Conversation` | |
| `DELETE /conversations/{id}` | — | 204 | |
| `DELETE /conversations` | — | `{deleted: number}` | all of the user's conversations |
| `PUT /messages/{id}/feedback` | `{rating: 1 \| -1, reasons?, comment?}` | feedback | assistant messages only |
| `DELETE /messages/{id}/feedback` | — | 204 | |
| `POST /search` | `{query, category?, top_k?, rerank?}` | `{query, search_query, grounded, gate_score, results: Source[], timings}` | |
| `GET /documents` | `?category=` | `DocumentSummary[]` | |
| `GET /documents/{doc_id}` | — | `DocumentSummary` | |
| `GET /documents/{doc_id}/outline` | — | `{doc_id, name, sections:[{section, page_number, passages}]}` | |
| `GET /documents/{doc_id}/pages/{n}` | — | `{doc_id, name, page_number, total_pages, passages:[{chunk_id, seq, section, text}]}` | |
| `GET /documents/{doc_id}/file` | — | `application/pdf` | inline |
| `POST /admin/documents` | multipart: `file, name, category, circular_id?, subcategory?, date?, issuer?, url?, replace?` | `{document, job}` (202) | 409 exists, 413 too big, 415 not PDF |
| `PATCH /admin/documents/{doc_id}` | metadata fields | `{document, job}` | reindexes |
| `POST /admin/documents/{doc_id}/reindex` | — | `IngestJob` (202) | |
| `POST /admin/reindex` | — | `{jobs: IngestJob[]}` | all documents |
| `DELETE /admin/documents/{doc_id}` | `?delete_file=false` | `{deleted, doc_id, file_deleted}` | 409 if job running |
| `GET /admin/jobs` / `GET /admin/jobs/{id}` | — | `IngestJob[]` / `IngestJob` | poll every 2s |
| `GET /admin/stats` | `?days=7` | `{usage, index, documents}` | |
| `POST /admin/cache/clear` | — | 204 | |

```ts
export interface DocumentSummary {
  doc_id: string; name: string; circular_id: string; category: string; subcategory: string;
  date: string; issuer: string; source_url: string; filename: string;
  has_file: boolean; chunks: number; indexed: boolean;
}
export interface IngestJob {
  id: string; doc_id: string; filename: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: "parsing" | "chunking" | "embedding" | "done" | null;
  progress: number; result: Record<string, unknown> | null; error: string | null;
  created_at: string; started_at: string | null; finished_at: string | null;
}
```

### 8.4 Error handling

Every non-2xx response has the shape `{"error": {"code", "message", "request_id", "details?"}}`.

| HTTP | `code` | UI behaviour |
|---|---|---|
| 400 | `invalid_user_id`, `invalid_page`, `bad_request` | toast with message (bug: log it) |
| 401 | `unauthorized` | BFF misconfiguration: log; show "Service unavailable" |
| 404 | `conversation_not_found`, `message_not_found`, `document_not_found` | redirect to `/` with a toast, or show a not-found page |
| 409 | `document_exists`, `job_running` | inline form error / disable action |
| 413 / 415 | `file_too_large` / `invalid_file` | inline upload error |
| 422 | `validation_error` (`details: [{field, message}]`) | map to form fields |
| 429 | `rate_limited` (`Retry-After` header) | toast "You're asking quickly — try again in Ns", disable send with countdown |
| 503 | `llm_unavailable`, `auth_not_configured`, `admin_disabled` | banner "Assistant temporarily unavailable", retry button |
| 500 | `internal_error` | toast "Something went wrong" + "Copy error ID" (request_id) |

Stream `error` events with code `rate_limited` behave like a 429 (default countdown 30s).

---

## 9. Reference implementation

### 9.1 Server-side API client (BFF)

```ts
// lib/api/server.ts  (server-only)
import "server-only";
import { auth } from "@/auth";

const BASE = `${process.env.COMPLIANCEIQ_API_URL}/api/v1`;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public requestId?: string,
              public details?: unknown, public retryAfter?: number) { super(message); }
}

export async function backendHeaders(opts: { admin?: boolean } = {}) {
  const session = await auth();
  if (!session?.user?.id) throw new ApiError(401, "unauthenticated", "Sign in required");
  const h: Record<string, string> = {
    "X-API-Key": process.env.COMPLIANCEIQ_API_KEY!,
    "X-User-Id": session.user.id,
    "X-Request-ID": crypto.randomUUID(),
  };
  if (opts.admin) {
    if (session.user.role !== "admin") throw new ApiError(403, "forbidden", "Admins only");
    h["X-Admin-Key"] = process.env.COMPLIANCEIQ_ADMIN_KEY!;
  }
  return h;
}

export async function api<T>(path: string, init: RequestInit & { admin?: boolean } = {}): Promise<T> {
  const headers = { ...(await backendHeaders({ admin: init.admin })), ...(init.headers as Record<string, string>) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers, cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, body?.error?.code ?? "error", body?.error?.message ?? res.statusText,
      body?.error?.request_id, body?.error?.details, Number(res.headers.get("retry-after")) || undefined);
  }
  return body as T;
}
```

### 9.2 Streaming proxy route

```ts
// app/api/chat/stream/route.ts
import { backendHeaders } from "@/lib/api/server";

export const runtime = "nodejs";          // keep long-lived streams off the edge runtime
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const body = await req.text();
  const upstream = await fetch(`${process.env.COMPLIANCEIQ_API_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: { ...(await backendHeaders()), "Content-Type": "application/json", Accept: "text/event-stream" },
    body,
    signal: req.signal,                    // client abort → upstream abort
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), { status: upstream.status,
      headers: { "Content-Type": "application/json" } });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
```

### 9.3 Browser SSE client (POST + fetch; `EventSource` can't POST)

```ts
// lib/chat/stream.ts
import type { ChatRequest, StreamEvent } from "@/lib/api/types";

export async function* streamChat(req: ChatRequest, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null);
    throw Object.assign(new Error(err?.error?.message ?? "Request failed"), {
      status: res.status, code: err?.error?.code, retryAfter: Number(res.headers.get("retry-after")) || undefined,
    });
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = frame.split("\n").filter(l => l.startsWith("data:")).map(l => l.slice(5).trimStart()).join("\n");
      if (!data || data === "[DONE]") continue;
      yield JSON.parse(data) as StreamEvent;
    }
  }
}
```

### 9.4 Stream state (Zustand) and reducer

```ts
// lib/chat/store.ts
type Stage = "idle" | "understanding" | "searching" | "thinking" | "writing" | "verifying" | "revising" | "done" | "error" | "stopped";

interface ActiveAnswer {
  stage: Stage; statusText: string; text: string; sources: Source[];
  mode: ResponseMode | null; verification: Verification | null; revised: boolean;
  confidence: Confidence; messageId: string | null; error?: { code: string; message: string };
}

export function reduce(s: ActiveAnswer, e: StreamEvent): ActiveAnswer {
  switch (e.type) {
    case "status": return { ...s, stage: e.stage, statusText: e.message };
    case "retrieval": return { ...s, sources: e.sources, mode: e.mode };
    case "token": return { ...s, text: s.text + e.content };
    case "revision": return { ...s, text: e.answer, mode: e.mode, revised: true, sources: e.sources ?? s.sources };
    case "verification": return e.final ? { ...s, verification: e } : s;
    case "done": return { ...s, stage: "done", text: e.answer, mode: e.mode, confidence: e.confidence, messageId: e.message_id };
    case "error": return { ...s, stage: "error", error: { code: e.code, message: e.message } };
    default: return s;
  }
}
```

Batch token updates: append to a ref and flush to state once per `requestAnimationFrame`, so React doesn't re-render per token.

On `conversation`: if the URL is `/`, call `router.replace('/c/' + id)` **without** remounting the chat, using `window.history.replaceState` or a layout that keeps the chat client mounted. Prepend the conversation to the sidebar cache.

On `done`: invalidate `["conversation", id]` and `["conversations"]` queries.

### 9.5 Rendering citations in markdown

```tsx
// components/chat/answer-markdown.tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CITE = /\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)(?:,\s*p\.?\s*\d+)?\]/g;

function withCitations(text: string, sources: Source[], onCite: (n: number) => void) {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    out.push(text.slice(last, m.index));
    const nums = m[1].split(/\s*,\s*/).flatMap(p => {
      const [a, b] = p.split(/\s*[–-]\s*/).map(Number);
      return b ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : [a];
    });
    nums.forEach(n => out.push(<CitationChip key={`${m.index}-${n}`} n={n} source={sources[n - 1]} onClick={() => onCite(n)} />));
    last = m.index! + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

export function AnswerMarkdown({ text, sources, onCite }: { text: string; sources: Source[]; onCite: (n: number) => void }) {
  const map = (children: React.ReactNode) =>
    React.Children.map(children, c => (typeof c === "string" ? withCitations(c, sources, onCite) : c));
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={{
        p: ({ children }) => <p>{map(children)}</p>,
        li: ({ children }) => <li>{map(children)}</li>,
        td: ({ children }) => <td>{map(children)}</td>,
        a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
```

During streaming, a citation may arrive split across tokens (for example `[` and then `1]`). The regex only matches complete brackets, so partial text renders as plain characters until it completes.

---

## 10. Component inventory

| Component | Responsibility | Key props |
|---|---|---|
| `AppShell` | sidebar + main + sources panel layout | `children` |
| `ConversationSidebar` | grouped list, search, actions, infinite scroll | — |
| `ConversationRow` | title, inline rename, menu | `conversation` |
| `ChatView` | message list + composer, owns stream lifecycle | `conversationId?` |
| `MessageList` | virtualized list (react-virtuoso) and auto-scroll unless the user scrolled up | `messages, active` |
| `UserMessage` | bubble, edit-and-resend | `message` |
| `AssistantMessage` | badges, banner, markdown, source row, actions | `message \| active` |
| `StatusLine` | stage icon + label | `stage, text` |
| `AnswerMarkdown` | markdown + `CitationChip`s | `text, sources, onCite` |
| `CitationChip` | `[n]` chip + HoverCard preview | `n, source?` |
| `ModeBadge` / `VerificationBadge` / `ConfidenceMeter` | trust indicators | `mode` / `verification` / `confidence` |
| `VerificationPopover` | details of claims checked | `verification, revised` |
| `GeneralModeBanner` / `NotFoundCard` | special modes | `onAction` |
| `SourcesPanel` / `SourceCard` | evidence list | `sources, highlighted` |
| `FeedbackBar` | 👍 👎 with reasons popover | `messageId, feedback` |
| `Composer` | textarea, selectors, send/stop | `onSend, onStop, streaming` |
| `RegulatorSelect` / `AnswerModeSelect` | from `/meta` | `value, onChange` |
| `SuggestionGrid` | empty state suggestions | `category` |
| `DocumentTable`, `DocumentOutline`, `PassageViewer`, `PdfFrame` | library and reader | `docId, page, chunkId` |
| `UploadDialog`, `JobProgress`, `StatsCards` | admin | — |
| `RetryAfterCountdown` | disables send during a 429 | `seconds` |

---

## 11. Data fetching (TanStack Query)

| Query key | Fetcher (BFF route) | staleTime |
|---|---|---|
| `["meta"]` | `GET /api/meta` | 1h |
| `["suggestions", category]` | `GET /api/suggestions?category=` | 1h |
| `["conversations", {q, archived}]` | `GET /api/conversations` (infinite) | 30s |
| `["conversation", id]` | `GET /api/conversations/:id` | 0 (refetch on focus off) |
| `["documents", category]` | `GET /api/documents` | 5m |
| `["document", docId]`, `["outline", docId]`, `["page", docId, n]` | … | 10m |
| `["admin", "stats", days]`, `["admin", "jobs"]` | … | 15s / poll |

Mutations use optimistic updates for rename, pin, archive, delete, and feedback, with rollback on error.

---

## 12. Accessibility

- The streaming answer container has `aria-live="polite"` and `aria-busy` while streaming. Announce the stage changes, not every token.
- Citation chips are `<button>`s with `aria-label="Source 1: RBI Master Direction on KYC, page 33"`.
- Every control is keyboard reachable, focus rings are visible, and `Esc` closes popovers and stops streaming.
- Color is never the only signal: badges always include an icon and text.
- Contrast is AA at minimum in both themes.

**Keyboard shortcuts:**

| Shortcut | Action |
|---|---|
| `Ctrl/⌘ + K` | Search conversations |
| `Ctrl/⌘ + Shift + O` | New chat |
| `/` | Focus composer |
| `Ctrl/⌘ + .` | Toggle sources panel |

---

## 13. Security checklist

- Keep API and admin keys server-only (no `NEXT_PUBLIC_`), and verify with a bundle analyzer that none leak.
- All backend calls go through route handlers or server actions that check the session.
- Render markdown with `skipHtml`, open links with `rel="noopener noreferrer"`, and use no `dangerouslySetInnerHTML`.
- CSP: `default-src 'self'`; `frame-src 'self'` (the PDF goes through the BFF); `connect-src 'self'`.
- Rate limit the BFF per session as well. The backend limiter is per user id and in-memory, one instance only.
- Admin pages check the role in middleware **and** in each route handler.

---

## 14. Testing

- **Unit (Vitest):**
  - The SSE parser: split frames, `[DONE]`, multi-line data.
  - The stream reducer.
  - The citation parser, including ranges `[1-3]`, groups `[1, 2]`, and page suffix `[2, p.34]`.
- **Component (RTL):**
  - `AssistantMessage` in each mode, verification states, and the revision crossfade.
  - `FeedbackBar` flows.
- **E2E (Playwright + MSW):** mock `/api/chat/stream` with recorded event sequences:
  1. Grounded and verified.
  2. Revised (`verification{final:false}` → `revision`).
  3. Not found.
  4. General.
  5. A rate-limit error mid-stream.
  6. A user pressing Stop.

  Also cover an upload with job polling.

Recorded fixtures: capture real streams with
`curl -N -X POST $API/api/v1/chat/stream -H "X-API-Key: …" -H "Content-Type: application/json" -d '{"question":"…"}' > fixtures/grounded.sse`.

---

## 15. Suggested project structure

```
web/
├── app/
│   ├── (chat)/layout.tsx            # AppShell
│   ├── (chat)/page.tsx              # new chat
│   ├── (chat)/c/[id]/page.tsx
│   ├── search/page.tsx
│   ├── documents/page.tsx
│   ├── documents/[docId]/page.tsx
│   ├── admin/(…)/page.tsx
│   ├── settings/page.tsx
│   └── api/                         # BFF route handlers
│       ├── chat/route.ts            # POST → /chat
│       ├── chat/stream/route.ts     # POST → /chat/stream (pipe)
│       ├── conversations/[[...path]]/route.ts
│       ├── messages/[id]/feedback/route.ts
│       ├── search/route.ts
│       ├── documents/[[...path]]/route.ts   # includes /file passthrough
│       ├── meta/route.ts, suggestions/route.ts
│       └── admin/[[...path]]/route.ts       # role-checked, adds X-Admin-Key
├── components/{chat,sources,documents,admin,ui}/
├── lib/{api,chat,utils}/
├── auth.ts
└── tests/{unit,e2e,fixtures}/
```

---

## 16. Build milestones

1. **Foundation:** Next.js + Tailwind + shadcn, auth, the BFF client, `/meta`, theming, and the AppShell.
2. **Chat MVP:** streaming chat with stages, markdown, citation chips, sources panel, and conversation create/load.
3. **Trust UI:** mode banners, verification badge and popover, confidence meter, the not-found card, and revision handling.
4. **History:** the sidebar with groups, search, rename/pin/archive/delete, and infinite scroll.
5. **Feedback + copy/regenerate.**
6. **Library + document reader:** outline, passages with highlight, and the PDF tab.
7. **Search page.**
8. **Admin:** stats, upload with job polling, metadata edit, reindex, and delete.
9. **Polish:** accessibility pass, keyboard shortcuts, mobile layouts, E2E suite, and CSP.
