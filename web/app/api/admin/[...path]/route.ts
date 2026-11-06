import type { NextRequest } from "next/server";
import { ADMIN_COOKIE, isValidAdminToken } from "@/lib/server/admin";
import { allowlist, errorResponse, forward, isSameOrigin } from "@/lib/server/forward";

/**
 * Admin proxy: /api/admin/<path> → FastAPI /api/v1/admin/<path>, only for a signed-in admin
 * session. Not matched by proxy.ts, so large PDF uploads stream through unbuffered.
 */

export const maxDuration = 300;

const ALLOWED = allowlist([
  "documents",
  "documents/[^/]+",
  "documents/[^/]+/reindex",
  "reindex",
  "jobs",
  "jobs/[^/]+",
  "stats",
  "cache/clear",
]);

async function handle(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const sub = path.map(encodeURIComponent).join("/");
  if (!ALLOWED.test(sub)) return errorResponse(404, "not_found", "Not found.");
  if (!isValidAdminToken(request.cookies.get(ADMIN_COOKIE)?.value)) {
    return errorResponse(401, "admin_auth_required", "Sign in to the admin console.");
  }
  if (!isSameOrigin(request)) return errorResponse(403, "forbidden", "Cross-site request blocked.");
  return forward(request, `admin/${sub}`, { "X-Admin-Key": process.env.COMPLIANCEIQ_ADMIN_KEY ?? "" });
}

export { handle as GET, handle as POST, handle as PATCH, handle as DELETE };
