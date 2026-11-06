# ComplianceIQ Web

Next.js frontend for ComplianceIQ: streaming, cited compliance answers with verification badges,
a sources panel, conversation history, a document library and reader, and passage search.

Built against the FastAPI backend in the repo root (`/api/v1`). Product and UX spec:
[`docs/FRONTEND_NEXTJS.md`](../docs/FRONTEND_NEXTJS.md). Backend contract: [`docs/API.md`](../docs/API.md).

## Run it

Start the backend first (repo root):

```powershell
$env:API_KEYS="<choose-a-key>"
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
- **Settings** — theme, default regulator and mode, follow-ups, auto-open sources, delete all.
- Keyboard: Ctrl+Shift+O new chat, Ctrl+K search chats, `/` focus composer, Esc stop.

## How it fits together

```
Browser ── /api/<path> ──▶ app/api/[...path]/route.ts ── /api/v1/<path> ──▶ FastAPI
                             adds X-API-Key, X-User-Id, X-Request-ID
                             streams bodies through, forwards aborts
```

- **One catch-all BFF route** (`app/api/[...path]/route.ts`) proxies an allowlist of backend
  paths. Admin routes are not exposed. The API key never reaches the browser.
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
app/api/[...path]/   BFF proxy to FastAPI
proxy.ts             anonymous user cookie
components/chat/     chat view, messages, composer, citations, sources panel, badges
components/shell/    app shell, sidebar, conversation rows, settings
components/documents/, components/search/
lib/api/             types + fetch client
lib/chat/            SSE parser, reducer, run store
lib/                 queries, settings, UI store, formatting, citations, export
```
