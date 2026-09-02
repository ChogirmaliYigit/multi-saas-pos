import { API_V1, env } from "@/lib/env";
import { ApiError } from "./errors";
import {
  getAccessToken,
  isAccessTokenExpired,
  setAccessToken,
} from "./token-store";
import type { ApiErrorBody } from "./types";

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip the Authorization header (login, signup, public reads). */
  anonymous?: boolean;
  /** Internal: prevents infinite refresh recursion. */
  _retried?: boolean;
  query?: Record<string, string | number | boolean | undefined | null>;
}

/**
 * A single in-flight refresh shared by every caller.
 *
 * A POS screen fires several queries at once; without this, a expired token
 * would trigger one refresh per query, and because refresh tokens are
 * single-use the extra ones would look like token *reuse* to the backend --
 * which revokes every session and logs the cashier out mid-sale.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      // Same-origin Route Handler: the browser attaches the httpOnly refresh
      // cookie automatically, and it never touches JavaScript.
      const response = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      const data = (await response.json()) as {
        access_token: string;
        expires_in: number;
      };
      setAccessToken(data.access_token, data.expires_in);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(
    path.startsWith("http") ? path : `${env.apiUrl}${API_V1}${path}`,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

export async function apiFetch<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, anonymous, _retried, query, headers, ...init } = options;

  // Refresh proactively when we already know the token is stale, rather than
  // spending a round trip to be told 401.
  if (!anonymous && isAccessTokenExpired() && !_retried) {
    await refreshAccessToken();
  }

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");
  if (body !== undefined) {
    requestHeaders.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (!anonymous && token) {
    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(buildUrl(path, query), {
    ...init,
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
    // The API is cross-origin and authenticated by header, not cookie.
    credentials: "omit",
  });

  if (response.status === 401 && !anonymous && !_retried) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, _retried: true });
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, (payload ?? {}) as Partial<ApiErrorBody>);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};

/**
 * Download an authenticated file.
 *
 * A plain <a href> cannot carry the bearer token, and the report endpoint is
 * deliberately behind auth -- an export holds a shop's entire trading history.
 * So the file is fetched with the token, turned into a blob URL, and handed to
 * a synthetic link. The object URL is revoked afterwards; leaking one pins the
 * whole file in memory for the life of the tab.
 */
export async function downloadFile(
  path: string,
  fallbackName: string,
): Promise<void> {
  if (isAccessTokenExpired()) {
    await refreshAccessToken();
  }
  const token = getAccessToken();

  const response = await fetch(buildUrl(path), {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: "omit",
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, payload as Partial<ApiErrorBody>);
  }

  // Prefer the server's filename; it already encodes the report type and period.
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename\*?=(?:utf-8'')?"?([^";]+)"?/i.exec(disposition);
  const filename = match ? decodeURIComponent(match[1]) : fallbackName;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
