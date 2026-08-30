// Auth token storage.
//
// Stored in a plain cookie (not httpOnly) rather than localStorage so
// middleware.ts can check for its presence server-side to gate /dashboard
// routes. Being JS-readable means it's not meaningfully more exposed to
// XSS than localStorage would be — same trade-off, chosen for the
// middleware benefit. See README for why this project doesn't go further
// (httpOnly + refresh rotation) — that's genuinely more than this
// portfolio-scale app's auth needs to be.

const COOKIE_NAME = 'nusaflow_token';
const COOKIE_MAX_AGE_DAYS = 7;

export function setToken(token: string) {
  const maxAge = COOKIE_MAX_AGE_DAYS * 24 * 60 * 60;
  document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

export function getToken(): string | null {
  if (typeof document === 'undefined') return null; // server-side render guard
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export function clearToken() {
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
}

export const AUTH_COOKIE_NAME = COOKIE_NAME;
