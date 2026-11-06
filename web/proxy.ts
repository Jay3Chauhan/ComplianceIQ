import { NextResponse, type NextRequest } from "next/server";
import { ADMIN_COOKIE, isValidAdminToken } from "@/lib/server/admin";
import { USER_COOKIE, USER_HEADER, isValidUserId, newUserId } from "@/lib/server/identity";

/**
 * 1. Gives every browser a stable anonymous user id. The backend scopes conversations and
 *    feedback by it (X-User-Id). Swap this for your auth provider's user id when adding sign-in.
 * 2. Sends /admin pages to the sign-in page unless the admin session cookie is valid.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    const signedIn = isValidAdminToken(request.cookies.get(ADMIN_COOKIE)?.value);
    const onLogin = pathname === "/admin/login";
    if (!signedIn && !onLogin) {
      const url = new URL("/admin/login", request.url);
      url.searchParams.set("next", pathname + search);
      return NextResponse.redirect(url);
    }
    if (signedIn && onLogin) return NextResponse.redirect(new URL("/admin", request.url));
  }

  if (isValidUserId(request.cookies.get(USER_COOKIE)?.value)) return NextResponse.next();

  const uid = newUserId();
  const headers = new Headers(request.headers);
  headers.set(USER_HEADER, uid);
  const response = NextResponse.next({ request: { headers } });
  response.cookies.set(USER_COOKIE, uid, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 365 * 2,
  });
  return response;
}

export const config = {
  // api/admin is excluded because proxy buffers request bodies (10 MB cap), which would cut off PDF uploads.
  matcher: ["/((?!_next/static|_next/image|api/admin|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp|ico)$).*)"],
};
