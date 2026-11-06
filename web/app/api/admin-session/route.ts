import { NextResponse, type NextRequest } from "next/server";
import {
  ADMIN_COOKIE,
  adminConfigured,
  adminCookieOptions,
  checkPassword,
  clearFailedLogins,
  createAdminToken,
  isValidAdminToken,
  loginThrottle,
  recordFailedLogin,
} from "@/lib/server/admin";
import { errorResponse, isSameOrigin } from "@/lib/server/forward";

/** GET: is the admin console enabled / am I signed in. POST: sign in. DELETE: sign out. */

export async function GET(request: NextRequest) {
  return Response.json({
    enabled: adminConfigured(),
    authenticated: isValidAdminToken(request.cookies.get(ADMIN_COOKIE)?.value),
  });
}

export async function POST(request: NextRequest) {
  if (!adminConfigured()) return errorResponse(404, "admin_disabled", "The admin console is not enabled on this server.");
  if (!isSameOrigin(request)) return errorResponse(403, "forbidden", "Cross-site request blocked.");

  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
  const wait = loginThrottle(ip);
  if (wait) {
    const res = errorResponse(429, "too_many_attempts", `Too many attempts. Try again in ${Math.ceil(wait / 60)} min.`);
    res.headers.set("Retry-After", String(wait));
    return res;
  }

  const body = (await request.json().catch(() => null)) as { password?: unknown } | null;
  const password = typeof body?.password === "string" ? body.password : "";
  if (!checkPassword(password)) {
    recordFailedLogin(ip);
    return errorResponse(401, "invalid_password", "Incorrect password.");
  }

  clearFailedLogins(ip);
  const res = NextResponse.json({ enabled: true, authenticated: true });
  res.cookies.set(ADMIN_COOKIE, createAdminToken(), adminCookieOptions);
  return res;
}

export async function DELETE(request: NextRequest) {
  if (!isSameOrigin(request)) return errorResponse(403, "forbidden", "Cross-site request blocked.");
  const res = NextResponse.json({ enabled: adminConfigured(), authenticated: false });
  res.cookies.set(ADMIN_COOKIE, "", { ...adminCookieOptions, maxAge: 0 });
  return res;
}
