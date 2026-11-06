# ComplianceIQ Web

Next.js frontend for ComplianceIQ: streaming, cited compliance answers with verification badges,
a sources panel, conversation history, a document library and reader, passage search, and an
admin console for documents, indexing jobs and usage analytics.

Built against the FastAPI backend in the repo root (`/api/v1`). Product and UX spec:
[`docs/FRONTEND_NEXTJS.md`](../docs/FRONTEND_NEXTJS.md). Backend contract: [`docs/API.md`](../docs/API.md).

## Run it

Start the backend first (repo root):

```powershell
$env:API_KEYS="<choose-a-key>"
$env:ADMIN_API_KEY="<choose-an-admin-key>"   # only needed for the admin console
uvicorn api.main:app --port 8000
```

Then the web app:

```powershell
cd web
npm install
copy .env.example .env.local   # set COMPLIANCEIQ_API_URL and COMPLIANCEIQ_API_KEY
npm run dev                    # http://localhost:3000
```

| Variable | Purpose |
|---|---|
| `COMPLIANCEIQ_API_URL` | FastAPI base URL, no trailing slash (e.g. `http://127.0.0.1:8000`) |
| `COMPLIANCEIQ_API_KEY` | One of the backend's `API_KEYS`. Server-only; never prefix with `NEXT_PUBLIC_` |
| `COMPLIANCEIQ_ADMIN_KEY` | Optional. The backend's `ADMIN_API_KEY`; enables the admin console together with `ADMIN_PASSWORD` |
| `ADMIN_PASSWORD` | Optional. Password for `/admin` |
| `ADMIN_SESSION_SECRET` | Optional. Signing secret for admin sessions (derived from the two values above if unset) |

Checks: `npm run lint`, `npm run typecheck`, `npm run build`.

## Features

- **Chat** — token streaming over SSE, live status ("Searching…", "Checking every claim…"),
  stop (Esc), regenerate, edit-and-resend (ArrowUp edits the last question), follow-up
  suggestions, AI titles, regulator filter and answer mode per conversation.
- **Trust signals** — inline `[n]` citation chips with hover previews, a docked sources panel
  (sheet on smaller screens), verification badge with flagged issues, confidence meter,
  distinct banners for general-knowledge and "not found" answers.
- **Reliability** — answers are generated and saved by the backend, so closing the tab loses
  nothing; reopening a conversation that is still answering polls until it finishes. A
  conversation that is busy elsewhere shows a toast with a "Stop it" action.
- **History** — grouped by date, search (Ctrl+K), rename, pin, archive, delete, export to
  Markdown/JSON, infinite scroll.
- **Library** — document grid by regulator, reader with outline, page passages (deep links
  highlight the cited passage), embedded PDF, "Ask about this".
- **Passage search** — direct hybrid search with optional reranking, no LLM call.
- **Settings** — theme, default regulator and mode, follow-ups (disabled when the server turns
  them off), auto-open sources, delete all, and an "About and status" section with the API
  version, models, enabled features and live `/ready` health.
- **Connection banner** — explains when the API is unreachable or misconfigured, with Retry.
- **Keyboard** — Ctrl+Shift+O new chat, Ctrl+K search chats, `/` focus composer, Esc stop,
  `?` shows all shortcuts.

## Admin console (`/admin`)

Enabled when `ADMIN_PASSWORD` and `COMPLIANCEIQ_ADMIN_KEY` are set. Signed-in admins also get an
Admin link in the sidebar.

- **Overview** — questions, grounded rate, verified rate, latency p50/p95 and helpfulness for
  1, 7, 30 or 90 days; how questions were answered; verification breakdown; recently unanswered
  questions (with "Try it"); index and coverage; live service health; clear caches; re-index all.
- **Documents** — every registered document with passages and index status; add a PDF
  (drag and drop, metadata form, replace an existing file); edit metadata (re-indexes); re-index;
  remove (optionally deleting the PDF); a jobs panel with live stage and progress that refreshes
  the library when a job finishes.

Security model: the password produces an HMAC-signed, expiring (8 h), httpOnly, `SameSite=Strict`
cookie. Changing the password signs everyone out. Sign-in is throttled per IP. The admin proxy
(`app/api/admin/[...path]`) checks the session, rejects cross-site writes, allowlists paths and
only then adds `X-Admin-Key`. The key never reaches the browser.

## How it fits together

```
Browser ── /api/<path> ───────▶ app/api/[...path]/route.ts ─────── /api/v1/<path> ──────▶ FastAPI
                                  adds X-API-Key, X-User-Id, X-Request-ID
        ── /api/admin/<path> ─▶ app/api/admin/[...path]/route.ts ─ /api/v1/admin/<path> ─▶
                                  admin session required; adds X-Admin-Key
```

- **Two catch-all BFF routes** share `lib/server/forward.ts`: request and response bodies are
  streamed (SSE, PDF uploads and downloads), client aborts cancel the upstream request, and each
  route proxies only an allowlist of paths. Keys never reach the browser.
- `proxy.ts` skips `/api/admin` because Next.js buffers proxied request bodies (10 MB cap),
  which would cut off PDF uploads.
- **Anonymous identity** — `proxy.ts` gives each browser an httpOnly `ciq_uid` cookie, sent to
  the backend as `X-User-Id`, so conversations are private per browser without sign-in. To add
  real auth, set the user id from the session in `lib/server/identity.ts`.
- **Server state** — TanStack Query (`lib/queries.ts`).
- **Live answers** — a global Zustand store of runs (`lib/chat/store.ts`) feeds SSE events
  through a pure reducer (`lib/chat/reducer.ts`). When a run finishes, the conversation query is
  refreshed and the run removed; React keys stay stable so the streamed answer turns into the
  saved message without a flicker.
- **UI** — Tailwind v4, shadcn/ui (Radix), lucide icons, `next-themes`.

### Next.js 16 notes

- `cacheComponents` is on. Route params and `usePathname` on dynamic routes are read inside
  `<Suspense>`, and route segment configs like `runtime`/`dynamic` are not allowed.
- Visited routes are kept mounted but hidden (React `<Activity>`), so state survives navigation.
  The new-chat page resets itself when hidden (`chat-view.tsx`) so it always opens blank.
- Persisted Zustand stores use `skipHydration` and rehydrate in `components/providers.tsx` to
  avoid hydration mismatches.

## Layout

```
app/                 routes: / (new chat), /c/[id], /documents, /documents/[docId], /search
app/admin/           /admin (overview), /admin/documents, /admin/login
app/api/[...path]/   BFF proxy to FastAPI
app/api/admin/       admin BFF proxy;  app/api/admin-session/  sign in / out
proxy.ts             anonymous user cookie, /admin page gate
components/chat/     chat view, messages, composer, citations, sources panel, badges
components/shell/    app shell, sidebar, conversation rows, settings, shortcuts, connection banner
components/admin/    overview, documents manager, upload / edit / delete dialogs, sign-in
components/documents/, components/search/
lib/api/             types + fetch client (JSON and FormData)
lib/chat/            SSE parser, reducer, run store
lib/server/          forwarding, identity cookie, admin sessions (server-only)
lib/                 queries, admin queries, settings, UI store, formatting, citations, export
```
