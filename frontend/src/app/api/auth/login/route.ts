import { NextResponse } from "next/server";

import { REFRESH_COOKIE, callApi, refreshCookieOptions } from "@/lib/api/server";

/**
 * Auth BFF.
 *
 * The browser posts credentials here rather than straight to FastAPI so the
 * refresh token can be split off into an httpOnly cookie. Only the short-lived
 * access token is handed back to page JavaScript. Every *other* API call still
 * goes directly to NEXT_PUBLIC_API_URL -- this proxy exists solely to own the
 * one credential worth stealing.
 */
export async function POST(request: Request) {
  const body = await request.json();
  const upstream = await callApi("/auth/login", {
    method: "POST",
    body,
  });

  const payload = await upstream.json().catch(() => ({}));

  if (!upstream.ok) {
    return NextResponse.json(payload, { status: upstream.status });
  }

  const response = NextResponse.json({
    access_token: payload.access_token,
    expires_in: payload.expires_in,
    token_type: payload.token_type,
  });
  response.cookies.set(REFRESH_COOKIE, payload.refresh_token, refreshCookieOptions);
  return response;
}
