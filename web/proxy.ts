import { NextResponse, type NextRequest } from "next/server";
import { USER_COOKIE, USER_HEADER, isValidUserId, newUserId } from "@/lib/server/identity";

/**
 * Gives every browser a stable anonymous user id. The backend scopes conversations and
 * feedback by it (X-User-Id). Swap this for your auth provider's user id when adding sign-in.
 */
export function proxy(request: NextRequest) {
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
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp|ico)$).*)"],
};
