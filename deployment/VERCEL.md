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

---

## Two things that cost real time on the first deploy

**`output: "standalone"` silently produces an empty deployment.** The build
compiles, generates static pages, reports success — and Vercel ends up with
nothing to serve, because standalone writes to `.next/standalone` where its
pipeline does not look. Every host then answers `DEPLOYMENT_NOT_FOUND`, which
reads like a domain misconfiguration and sends you to the DNS panel. It is not.
`next.config.ts` now disables standalone when `process.env.VERCEL` is set, and
keeps it for the self-hosted image.

**The apex and `www` are not interchangeable.** `www` uses a CNAME to
`cname.vercel-dns.com` and works as soon as it propagates. The apex needs an A
record, and if the domain previously pointed somewhere else, resolvers keep
answering with the *old* IP until that record's TTL expires — up to several
hours. During that window the apex alternates between working and failing to
connect, while `www` is fine throughout.

Check the authoritative servers rather than a public resolver before assuming
the zone is wrong:

```bash
dig @rdns1.your-registrar joinpay.uz A +short   # what the zone says
dig joinpay.uz A @8.8.8.8 +short                # what the internet remembers
```
