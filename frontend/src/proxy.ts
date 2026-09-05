import { NextResponse, type NextRequest } from "next/server";

import { extractTenantSlug } from "@/lib/tenant";

const BASE_DOMAIN = process.env.NEXT_PUBLIC_BASE_DOMAIN ?? "localhost:3000";
const REFRESH_COOKIE = "pos_refresh";

/** Routes reachable without a session. */
const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/forgot-password",
  // Reached from an email link, by someone who cannot sign in.
  "/reset-password",
];

/**
 * Runs on every matched request, before routing (Next 16 renamed this
 * convention from `middleware` to `proxy`).
 *
 * Two jobs:
 *
 * 1. Resolve the tenant subdomain and pass it down as a request header, so
 *    server components know which shop they are rendering without re-parsing
 *    the Host everywhere.
 * 2. A cheap first-pass redirect for unauthenticated visitors.
 *
 * The redirect is convenience only. Middleware cannot verify a JWT signature
 * without the backend secret -- and putting that secret in the edge runtime
 * would be worse than the problem it solves -- so it checks only for the
 * presence of the refresh cookie. Real authorisation happens in the API on
 * every request.
 */
export default function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const host = request.headers.get("host");
  const tenantSlug = extractTenantSlug(host, BASE_DOMAIN);

  const requestHeaders = new Headers(request.headers);
  if (tenantSlug) {
    requestHeaders.set("x-tenant-slug", tenantSlug);
  } else {
    requestHeaders.delete("x-tenant-slug");
  }

  const isPublic = PUBLIC_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
  const hasSession = request.cookies.has(REFRESH_COOKIE);

  if (!isPublic && !hasSession && pathname !== "/") {
    const loginUrl = new URL("/login", request.url);
    // Preserve where they were headed so sign-in can return them there.
    if (pathname !== "/login") {
      loginUrl.searchParams.set("next", `${pathname}${search}`);
    }
    return NextResponse.redirect(loginUrl);
  }

  if (isPublic && hasSession) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    /*
     * Everything except Next internals, the auth BFF (which must stay
     * reachable while signed out), and static files.
     */
    "/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
