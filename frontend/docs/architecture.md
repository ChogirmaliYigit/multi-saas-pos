# Frontend — Step 3

Next.js 16 (App Router) · React 19 · Tailwind 4 · shadcn/ui (radix-nova) ·
Zustand · TanStack Query · Framer Motion.

## Where the tokens live, and why

This is the decision everything else hangs off.

| Credential | Stored in | Reachable by page JS |
|---|---|---|
| Access token (30 min, 12 h for cashiers) | Module variable in memory | Yes — it has to be, it goes in a header |
| Refresh token (30 days) | `httpOnly` `SameSite=Lax` cookie | **No** |

A POS terminal runs all day on a shared device. Anything in `localStorage` is
readable by any script that manages to execute on the page, so the long-lived
credential is never handed to JavaScript at all.

That requires a small **auth BFF**: four Route Handlers under
`/api/auth/*` that call FastAPI server-side and split the refresh token off
into a cookie. Everything else — every product, order and report call — goes
**directly** to `NEXT_PUBLIC_API_URL` from the browser with a bearer token, so
this is not a general-purpose proxy. It exists to own the one credential worth
stealing.

The cost is that a page reload drops the access token. `SessionProvider` pays
it back by calling `/api/auth/refresh` on mount; `isReady` in the auth store is
what stops that handshake from flashing the login screen on every reload.

Verified in the browser: `document.cookie` is empty on an authenticated page,
and `localStorage` holds only `theme` and `pos-ui-preferences`.

## Single-flight refresh

Refresh tokens are single-use, and the backend treats a replayed one as theft —
it revokes every session for that user. A POS screen fires several queries at
once, so an expired token would trigger one refresh per query and the extra
ones would look exactly like an attack, logging the cashier out mid-sale.
`src/lib/api/client.ts` therefore shares one in-flight refresh promise across
all callers.

## Three route groups, three shells

| Group | Roles | Shell |
|---|---|---|
| `(auth)` | anonymous | Centred card, scrollable |
| `(shop)` | owner, manager | Sidebar + topbar, max-w-7xl |
| `(platform)` | super_admin | Sidebar + topbar, no POS link |
| `pos` | cashier, manager, owner | `fixed inset-0`, no page scroll |

The terminal is a fixed-viewport application, not a document: grid and cart
scroll independently and the page itself never does.

## What the client-side guards are and are not

`AuthGuard` and `PermissionGate` decide what to **render**. They are UX, not
security. The permission list comes from `/auth/me`, so the sidebar shows
exactly what the API will allow — but the API re-checks every request, and
`src/lib/permissions.ts` is a mirror of `app/core/permissions.py` with no
authority of its own.

`src/proxy.ts` (Next 16 renamed the `middleware` convention) does two things:
resolves the tenant subdomain into an `x-tenant-slug` request header, and
redirects visitors with no refresh cookie to `/login`. That redirect is
convenience only — the edge runtime cannot verify a JWT signature without the
backend secret, and putting that secret at the edge would be worse than the
problem it solves.

## Subdomain tenancy

`shop1.saas-pos.com` → slug `shop1`, read from the `Host` header in the proxy
and passed down as a header. The login page uses it to skip the "shop address"
field. The slug only tells the API *which shop to look up credentials in*; it
never grants access, and the backend rejects a token whose shop does not match
the host it arrived on (verified: 403 `permission_denied`).

## Verified end to end

Against the real FastAPI backend and PostgreSQL:

```
1. login                 200 | access token to JS: true | refresh in body: false
2. refresh               200 | cookie rotated: true
3. replay old token      401 | Refresh token reuse detected; all sessions revoked
4. rotated token now     401 (family revoked)
5. own subdomain         200 | another shop's subdomain: 403 permission_denied
6. /dashboard signed out 307 -> /login?next=%2Fdashboard
```

Plus, in a real browser: sign-in through the form lands on the dashboard, both
themes render, the sidebar collapses, and an owner visiting `/platform` is
redirected to `/dashboard`.

`npm run build` succeeds (23 routes), `tsc --noEmit` and `eslint` are clean.

---

# Step 5 — Admin panel and charts

## The chart palette was computed, not chosen

Colours were run through the data-viz validator in both modes rather than
picked by eye. The set leads with the brand teal so a chart reads as part of
the product:

| | light | dark |
|---|---|---|
| slot 1 | `#0d9488` | `#10a396` |
| slot 2 | `#eb6834` | `#d95926` |
| slot 3 | `#2a78d6` | `#3987e5` |

All checks pass in both modes — lightness band, chroma floor, colour-blind
separation (worst adjacent ΔE 10.7 light / 13.5 dark), normal-vision separation
(27.5 / 26.5) and 3:1 contrast on the chart surface. The first candidate dark
teal (`#14b8a6`) **failed** the lightness band at L 0.704 and was re-stepped;
that is the kind of thing eyeballing does not catch.

Three slots is the cap — the validated palette only clears the all-pairs floors
for the first three, and the only categorical chart here (payment methods) has
exactly three. Every chart is otherwise single-series, so it uses one hue and
carries no legend: the card title names it, and a legend box for one thing is
furniture.

Payment split is a labelled bar rather than a pie: humans compare angles badly,
and every row is direct-labelled with name, amount and share, so identity never
depends on colour alone.

## Charts must not depend on requestAnimationFrame to be visible

Recharts animates marks behind an expanding `clipPath` driven by rAF. Whenever
rAF is throttled — a background tab, low power mode, a wall-mounted tablet just
brought back to focus — the clip stays collapsed and **the data is simply not
drawn**. Caught it stuck at 3.7px of 549. `isAnimationActive={false}` on every
data mark; the card still fades in, but the numbers inside it are just there.
It also sidesteps recharts ignoring `prefers-reduced-motion`.

## Typing the API honestly caught two real bugs

The product list was typed `Page<ProductDetail>` while the endpoint actually
returned `ProductOut`. Fixing the type to match reality surfaced both:

- **Cost `$0.00`, margin `NaN%`** on every row, because the field was never in
  the response. It is now returned — but only to callers who may see it.
- **Editing from a list row would have wiped each product's tax rate and
  description.** The row does not carry `tax_rate_id`, so a form seeded from it
  submitted `null` on save. The dialog now loads the full record by id first.

## Report polling has to survive an unfocused window

React Query suspends `refetchInterval` while the window is not focused. That is
the right default almost everywhere and exactly wrong for a background job: the
whole point is that you go and do something else. Coming back to a list still
showing "pending" for a report that finished minutes ago is worse than a
handful of extra requests, so the reports query sets
`refetchIntervalInBackground` and `refetchOnWindowFocus`.

## Downloads

`Content-Disposition` is not readable cross-origin unless the server exposes
it, so every download silently fell back to a generic filename. Added to the
API's `expose_headers`. The file itself is fetched with the bearer token and
handed to a synthetic link via a blob URL — a plain `<a href>` cannot carry
auth, and the endpoint is deliberately behind it.
