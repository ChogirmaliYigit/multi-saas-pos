import { NextResponse } from "next/server";

import { REFRESH_COOKIE, callApi, readRefreshCookie } from "@/lib/api/server";

export async function POST() {
  const refreshToken = await readRefreshCookie();

  if (refreshToken) {
    // Revoke server-side too. Dropping the cookie alone would leave a valid
    // token in the database for anyone who captured it.
    await callApi("/auth/logout", {
      method: "POST",
      body: { refresh_token: refreshToken },
    }).catch(() => null);
  }

  const response = NextResponse.json({ message: "Signed out." });
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}
