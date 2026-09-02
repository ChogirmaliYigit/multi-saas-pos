import { NextResponse } from "next/server";

import {
  REFRESH_COOKIE,
  callApi,
  readRefreshCookie,
  refreshCookieOptions,
} from "@/lib/api/server";

export async function POST() {
  const refreshToken = await readRefreshCookie();
  if (!refreshToken) {
    return NextResponse.json(
      { code: "unauthenticated", message: "No session." },
      { status: 401 },
    );
  }

  const upstream = await callApi("/auth/refresh", {
    method: "POST",
    body: { refresh_token: refreshToken },
  });
  const payload = await upstream.json().catch(() => ({}));

  if (!upstream.ok) {
    // Includes the reuse-detection case, where the backend has already
    // revoked every session. Clear the cookie so the app stops retrying.
    const failed = NextResponse.json(payload, { status: upstream.status });
    failed.cookies.delete(REFRESH_COOKIE);
    return failed;
  }

  const response = NextResponse.json({
    access_token: payload.access_token,
    expires_in: payload.expires_in,
    token_type: payload.token_type,
  });
  // Refresh tokens are single-use, so the rotated one replaces the cookie.
  response.cookies.set(REFRESH_COOKIE, payload.refresh_token, refreshCookieOptions);
  return response;
}
