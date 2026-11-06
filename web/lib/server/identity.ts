import type { NextRequest } from "next/server";

export const USER_COOKIE = "ciq_uid";
export const USER_HEADER = "x-ciq-uid";
const VALID = /^[A-Za-z0-9_-]{8,64}$/;

export function isValidUserId(value: string | undefined | null): value is string {
  return !!value && VALID.test(value);
}

export function newUserId(): string {
  return `u_${crypto.randomUUID().replaceAll("-", "")}`;
}

/** The anonymous per-browser id set by proxy.ts (header on the very first request, cookie afterwards). */
export function userIdFrom(req: NextRequest): string {
  const cookie = req.cookies.get(USER_COOKIE)?.value;
  if (isValidUserId(cookie)) return cookie;
  const header = req.headers.get(USER_HEADER);
  return isValidUserId(header) ? header : "anonymous";
}
