import type { NextRequest } from "next/server";
import { userIdFrom } from "@/lib/server/identity";

/**
 * Backend-for-frontend proxy: /api/<path> → FastAPI /api/v1/<path>.
 * Adds the server-only API key and the user id; streams every response body through
 * (SSE answers, PDFs, exports) and propagates client aborts upstream.
 */

export const maxDuration = 300;

const ALLOWED = new RegExp(
  "^(" +
    [
      "meta",
      "suggestions",
      "health",
      "ready",
      "search",
      "chat",
      "chat/stream",
      "conversations",
      "conversations/[^/]+",
      "conversations/[^/]+/(stop|export)",
      "messages/[^/]+",
      "messages/[^/]+/(regenerate|edit|feedback)",
      "documents",
      "documents/[^/]+",
      "documents/[^/]+/(outline|file)",
      "documents/[^/]+/pages/\\d+",
    ].join("|") +
    ")$",
);

const PASS_HEADERS = ["content-type", "content-disposition", "retry-after", "x-request-id", "cache-control"];

function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, request_id: null }, detail: message }, { status });
}

async function handle(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const sub = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.test(sub)) return errorResponse(404, "not_found", "Not found.");

  const base = process.env.COMPLIANCEIQ_API_URL?.replace(/\/+$/, "");
  if (!base) return errorResponse(500, "not_configured", "COMPLIANCEIQ_API_URL is not set on the web server.");

  const headers = new Headers({
    "X-API-Key": process.env.COMPLIANCEIQ_API_KEY ?? "",
    "X-User-Id": userIdFrom(request),
    "X-Request-ID": request.headers.get("x-request-id") ?? crypto.randomUUID(),
  });
  for (const name of ["content-type", "accept"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/api/v1/${sub}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return errorResponse(502, "backend_unreachable", "The ComplianceIQ API is not reachable. Is it running?");
  }

  const out = new Headers();
  for (const name of PASS_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  if (out.get("content-type")?.includes("text/event-stream")) {
    out.set("Cache-Control", "no-cache, no-transform");
    out.set("X-Accel-Buffering", "no");
    out.set("Connection", "keep-alive");
  }
  const body = upstream.status === 204 || upstream.status === 304 ? null : upstream.body;
  return new Response(body, { status: upstream.status, headers: out });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
