import { NextResponse } from "next/server";

import { REFRESH_COOKIE, callApi, refreshCookieOptions } from "@/lib/api/server";

/** Register a shop, then sign the new owner straight in. */
export async function POST(request: Request) {
  const body = await request.json();

  const created = await callApi("/auth/signup", { method: "POST", body });
  const createdPayload = await created.json().catch(() => ({}));
  if (!created.ok) {
    return NextResponse.json(createdPayload, { status: created.status });
  }

  const loggedIn = await callApi("/auth/login", {
    method: "POST",
    body: {
      email: body.email,
      password: body.password,
      tenant_slug: body.slug,
    },
  });
  const tokens = await loggedIn.json().catch(() => ({}));
  if (!loggedIn.ok) {
    // The shop exists; only the auto-login failed. Send them to sign in.
    return NextResponse.json(
      { ...createdPayload, requires_login: true },
      { status: 201 },
    );
  }

  const response = NextResponse.json(
    {
      user: createdPayload,
      access_token: tokens.access_token,
      expires_in: tokens.expires_in,
    },
    { status: 201 },
  );
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, refreshCookieOptions);
  return response;
}
