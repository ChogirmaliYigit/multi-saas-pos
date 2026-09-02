/**
 * The access token lives in a module variable -- never localStorage.
 *
 * Anything in localStorage is readable by any script that manages to run on
 * the page, and a POS terminal runs all day on a shared device. Keeping the
 * short-lived access token in memory means a page reload drops it, which is
 * why `/api/auth/refresh` is called on mount: the long-lived refresh token
 * sits in an httpOnly cookie that JavaScript cannot read at all.
 */

let accessToken: string | null = null;
let expiresAt = 0;

const listeners = new Set<(token: string | null) => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null, expiresIn?: number): void {
  accessToken = token;
  // Refresh 30s early so a request cannot start with a token that expires
  // while it is in flight.
  expiresAt = token && expiresIn ? Date.now() + (expiresIn - 30) * 1000 : 0;
  listeners.forEach((listener) => listener(token));
}

export function isAccessTokenExpired(): boolean {
  return !accessToken || Date.now() >= expiresAt;
}

export function onAccessTokenChange(
  listener: (token: string | null) => void,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearAccessToken(): void {
  setAccessToken(null);
}
