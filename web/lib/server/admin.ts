import { createHash, createHmac, timingSafeEqual } from "node:crypto";

/**
 * Admin console sessions. The backend's X-Admin-Key never leaves this server: an admin signs
 * in with ADMIN_PASSWORD and gets a signed, expiring, httpOnly cookie; the admin proxy checks
 * it and attaches the key.
 */

export const ADMIN_COOKIE = "ciq_admin";
export const ADMIN_TTL_SECONDS = 60 * 60 * 8;

export function adminConfigured(): boolean {
  return !!process.env.ADMIN_PASSWORD && !!process.env.COMPLIANCEIQ_ADMIN_KEY;
}

function sha256(value: string): Buffer {
  return createHash("sha256").update(value).digest();
}

// Includes the password, so changing ADMIN_PASSWORD signs every admin out.
function signingKey(): Buffer {
  const explicit = process.env.ADMIN_SESSION_SECRET;
  return explicit ? sha256(explicit) : sha256(`${process.env.COMPLIANCEIQ_ADMIN_KEY}:${process.env.ADMIN_PASSWORD}`);
}

function sign(payload: string): string {
  return createHmac("sha256", signingKey()).update(payload).digest("base64url");
}

function safeEqual(a: Buffer, b: Buffer): boolean {
  return a.length === b.length && timingSafeEqual(a, b);
}

export function checkPassword(input: string): boolean {
  const expected = process.env.ADMIN_PASSWORD;
  return !!expected && safeEqual(sha256(input), sha256(expected));
}

export function createAdminToken(): string {
  const exp = String(Math.floor(Date.now() / 1000) + ADMIN_TTL_SECONDS);
  return `${exp}.${sign(exp)}`;
}

export function isValidAdminToken(token: string | undefined | null): boolean {
  if (!token || !adminConfigured()) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !/^\d+$/.test(exp) || Number(exp) * 1000 < Date.now()) return false;
  return safeEqual(Buffer.from(sig), Buffer.from(sign(exp)));
}

export const adminCookieOptions = {
  httpOnly: true,
  sameSite: "strict" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
  maxAge: ADMIN_TTL_SECONDS,
};

const attempts = new Map<string, number[]>();
const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 8;

/** In-memory per-IP login throttle (per server instance). Returns seconds to wait, or 0. */
export function loginThrottle(ip: string): number {
  const now = Date.now();
  const recent = (attempts.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  attempts.set(ip, recent);
  return recent.length >= MAX_ATTEMPTS ? Math.ceil((recent[0] + WINDOW_MS - now) / 1000) : 0;
}

export function recordFailedLogin(ip: string): void {
  attempts.set(ip, [...(attempts.get(ip) ?? []), Date.now()]);
}

export function clearFailedLogins(ip: string): void {
  attempts.delete(ip);
}
