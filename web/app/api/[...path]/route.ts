import type { NextRequest } from "next/server";
import { allowlist, errorResponse, forward, isSameOrigin } from "@/lib/server/forward";
import { userIdFrom } from "@/lib/server/identity";

/**
 * Backend-for-frontend proxy: /api/<path> → FastAPI /api/v1/<path>.
 * Adds the server-only API key and the user id. Admin routes live in /api/admin/*.
 */

export const maxDuration = 300;

const ALLOWED = allowlist([
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
]);

async function handle(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const sub = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.test(sub)) return errorResponse(404, "not_found", "Not found.");
  if (!isSameOrigin(request)) return errorResponse(403, "forbidden", "Cross-site request blocked.");
  return forward(request, sub, { "X-User-Id": userIdFrom(request) });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
