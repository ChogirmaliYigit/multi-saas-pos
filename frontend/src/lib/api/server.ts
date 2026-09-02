import { cookies, headers } from "next/headers";

import { API_V1, env } from "@/lib/env";

export const REFRESH_COOKIE = "pos_refresh";

/**
 * The refresh token is the long-lived credential, so it is kept where page
 * JavaScript cannot reach it at all. Route Handlers set and read it; the
 * browser attaches it automatically on same-origin requests.
 */
export const refreshCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: env.isProduction,
  path: "/",
  maxAge: 60 * 60 * 24 * 30, // matches REFRESH_TOKEN_EXPIRE_DAYS
};

/** Server-to-server call to FastAPI, over the internal network in production. */
export async function callApi(
  path: string,
  init: Omit<RequestInit, "body"> & { body?: unknown } = {},
): Promise<Response> {
  const { body, headers: extraHeaders, ...rest } = init;
  const requestHeaders = new Headers(extraHeaders);
  requestHeaders.set("Accept", "application/json");
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }

  // Forward the Host so the backend resolves the tenant from the subdomain
  // exactly as it would for a direct browser call.
  const incoming = await headers();
  const forwardedHost = incoming.get("host");
  if (forwardedHost) {
    requestHeaders.set("Host", forwardedHost);
    requestHeaders.set("X-Forwarded-Host", forwardedHost);
  }

  return fetch(`${env.internalApiUrl}${API_V1}${path}`, {
    ...rest,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
}

export async function readRefreshCookie(): Promise<string | undefined> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value;
}
