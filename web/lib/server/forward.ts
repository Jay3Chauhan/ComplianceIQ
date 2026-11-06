import type { NextRequest } from "next/server";

const PASS_HEADERS = ["content-type", "content-disposition", "retry-after", "x-request-id", "cache-control"];

export function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message, request_id: null }, detail: message }, { status });
}

/**
 * Forwards a request to FastAPI `/api/v1/<sub>` with server-side headers. Request and
 * response bodies are streamed (SSE answers, PDF uploads/downloads, exports), and a client
 * abort cancels the upstream request.
 */
export async function forward(request: NextRequest, sub: string, extraHeaders: Record<string, string>): Promise<Response> {
  const base = process.env.COMPLIANCEIQ_API_URL?.replace(/\/+$/, "");
  if (!base) return errorResponse(500, "not_configured", "COMPLIANCEIQ_API_URL is not set on the web server.");

  const headers = new Headers({
    "X-API-Key": process.env.COMPLIANCEIQ_API_KEY ?? "",
    "X-Request-ID": request.headers.get("x-request-id") ?? crypto.randomUUID(),
    ...extraHeaders,
  });
  for (const name of ["content-type", "accept"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD" && request.body !== null;
  let upstream: Response;
  try {
    upstream = await fetch(`${base}/api/v1/${sub}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      signal: request.signal,
      cache: "no-store",
    } as RequestInit);
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

/** Builds an anchored allowlist regex from path patterns. */
export function allowlist(patterns: string[]): RegExp {
  return new RegExp(`^(${patterns.join("|")})$`);
}

/** Rejects cross-site state-changing requests (defence in depth on top of SameSite cookies). */
export function isSameOrigin(request: NextRequest): boolean {
  if (request.method === "GET" || request.method === "HEAD") return true;
  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).host === request.headers.get("host");
  } catch {
    return false;
  }
}
