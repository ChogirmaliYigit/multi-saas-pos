# Frontend on Vercel

## Order matters

`NEXT_PUBLIC_*` values are inlined into the client bundle **at build time**, not
read at runtime. So the API domain has to exist before the frontend is built,
or the deployed bundle points at nothing. Deploy the server first.

## Project settings

Import `ChogirmaliYigit/multi-saas-pos` in Vercel, then:

| Setting | Value | Why |
|---|---|---|
| **Root Directory** | `frontend` | The repo root is not the Next app. This is the single most common import failure. |
| Framework Preset | Next.js | Auto-detected |
| Build Command | *(default)* | `next build` |
| Node.js Version | 22.x | Matches the Docker image |

`output: "standalone"` in `next.config.ts` is for the optional self-hosted
image; Vercel ignores it.

## Environment variables

Set for **Production**, **Preview** and **Development**:

```
NEXT_PUBLIC_API_URL      = https://api.<your-domain>
NEXT_PUBLIC_BASE_DOMAIN  = <your-domain>
INTERNAL_API_URL         = https://api.<your-domain>
```

`INTERNAL_API_URL` is server-side only — the auth BFF routes use it. On Vercel
it is the same public URL, because the functions are not inside the VPS
network. On a self-hosted deployment it becomes `http://api:8000`.

None of these are secrets. The real credential, the refresh token, lives in an
httpOnly cookie the browser sets — no Vercel secret is involved.

## Domains

Two different jobs, and they resolve to two different places:

```
<your-domain>        -> Vercel     apex, marketing/login
*.<your-domain>      -> Vercel     tenant subdomains: shop1, shop2, ...
api.<your-domain>    -> the VPS    A record to the server IP
```

`api.` must **not** point at Vercel.

### About the wildcard

Subdomain tenancy needs `*.<your-domain>` on Vercel. **Wildcard domains
require a paid Vercel plan** — on Hobby you cannot add one.

If you are on Hobby, or want to avoid the wildcard, nothing needs to change in
the code. The app already supports a single host: the login form shows a "Shop
address" field whenever there is no subdomain, and sends `tenant_slug` in the
body instead. Point one domain at Vercel and it works — shops type their slug
once at sign-in rather than getting their own subdomain.

The backend accepts both paths; `extract_tenant_slug` simply returns `None` and
the JWT still carries the tenant.

## CORS

The API must allow the frontend's origin. In the server's `.env`:

```
CORS_ORIGINS=https://<your-domain>,https://www.<your-domain>
```

Every `*.<your-domain>` origin is already allowed by a regex, so tenant
subdomains do not need listing. After changing it: `docker compose up -d api`.

## Deploys

Vercel builds on every push to `main`. Because the API URL is baked in at build
time, changing it means triggering a **redeploy**, not just editing the
variable.
