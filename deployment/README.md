# Deployment

Backend on a VPS via Docker Compose; frontend on Vercel. The whole stack can
also run on one box (`--profile selfhost`).

## What runs where

| Service | Image | Exposed | Notes |
|---|---|---|---|
| `nginx` | nginx:1.27-alpine | **80, 443** | The only thing bound to the host |
| `api` | `pos-backend` | internal | Gunicorn + uvicorn workers |
| `worker` | `pos-backend` | internal | Celery: report generation |
| `beat` | `pos-backend` | internal | Scheduler; exactly one instance |
| `migrate` | `pos-backend` | — | One-shot, runs to completion first |
| `postgres` | postgres:16-alpine | internal | Volume `pgdata` |
| `redis` | redis:7-alpine | internal | AOF on, so queued jobs survive a restart |
| `certbot` | certbot/certbot | — | Renews twice daily |
| `frontend` | `pos-frontend` | internal | Profile `selfhost` only |

**Nothing but Nginx binds a host port.** Postgres on `0.0.0.0:5432` is found by
scanners within hours; here it is reachable only from the compose network.

## First deploy

```bash
git clone <repo> /srv/pos && cd /srv/pos

cp .env.example .env
./deployment/scripts/generate-secrets.sh >> .env   # fills the blank secrets
$EDITOR .env                                       # set BASE_DOMAIN, CORS_ORIGINS

./deployment/scripts/configure-nginx.sh saas-pos.com

# DNS first:
#   A  saas-pos.com      -> <ip>
#   A  api.saas-pos.com  -> <ip>
#   A  *.saas-pos.com    -> <ip>     (tenant subdomains)
CERTBOT_EMAIL=ops@saas-pos.com ./deployment/scripts/init-certs.sh saas-pos.com

docker compose up -d
make ps
```

## The two database roles

This is the detail that makes tenant isolation real, and it is easy to undo by
accident.

| Role | Used by | RLS applies |
|---|---|---|
| `POSTGRES_ADMIN_USER` (`pos`) | Alembic only | **No** — it owns the schema |
| `POSTGRES_APP_USER` (`pos_app`) | API, workers | **Yes** |

PostgreSQL exempts superusers *and table owners* from row-level security. If
the API ever connects with the admin credentials, every policy silently stops
applying while still looking perfect in `pg_policies`. The app role is created
by migration `0004` with DML grants only, and `NOSUPERUSER NOBYPASSRLS`.
`tests/test_rls.py` fails the build if that regresses.

## Certificates

Two are needed, and they are issued differently:

- **`api.<domain>`** — HTTP-01 via the webroot. Automated by `init-certs.sh`.
- **`<domain>` + `*.<domain>`** — a wildcard, because tenant subdomains are
  unbounded. Let's Encrypt only issues wildcards over **DNS-01**, which needs a
  provider plugin and an API token. `init-certs.sh` prints the exact command
  for your provider rather than pretending to automate it.

This is the most common thing to get stuck on, which is why the two paths are
kept visibly separate.

## Deploying a change

```bash
make deploy
```

`deploy.sh` builds images tagged with the git SHA, runs migrations **before**
starting any new container, rolls out, waits for `/health/ready`, and reverts
`IMAGE_TAG` if the health check fails.

One caveat it prints rather than hides: **a rollback does not revert
migrations.** If the schema change is not backward-compatible, rolling the
image back is not enough. Prefer expand/contract — add columns, deploy, then
remove the old ones in a later release.

## Backups

Install once, as the deploy user:

```bash
sudo ./deployment/scripts/install-backup-cron.sh
```

That creates `/var/backups/pos` (mode 0700 — dumps hold every shop's trading
history in the clear), sets up logrotate, and adds a nightly crontab entry for
the deploy user rather than root, because the job runs `docker compose`.

Each run writes a custom-format dump, refuses anything under 1KB, and verifies
the archive before pruning older ones. A truncated dump that still exits 0
looks like a backup right up until the day you need it.

**Verify that it actually restores**, periodically and after any schema change:

```bash
./deployment/scripts/verify-restore.sh
```

This restores the newest dump into a scratch database and checks the tables,
seeded plans, migration state, and that row-level security survived. That last
one matters: policies are schema objects, and a dump that quietly lost them
would restore a database with no tenant isolation at all. `pg_restore --list`
alone would not notice.

Manual restore:

```bash
docker compose exec -T postgres pg_restore -U pos -d pos --clean --if-exists < backup.dump
```

Note the dumps live on the same disk as the database. That covers a bad
migration or a mistaken `DELETE`; it does not cover losing the instance. Copy
them off the box — S3, or another host — before treating this as a real
backup strategy.

## Frontend on Vercel

Set in the Vercel project:

```
NEXT_PUBLIC_API_URL     = https://api.saas-pos.com
NEXT_PUBLIC_BASE_DOMAIN = saas-pos.com
INTERNAL_API_URL        = https://api.saas-pos.com
```

Add `*.saas-pos.com` as a wildcard domain so tenant subdomains resolve. Then
delete `deployment/nginx/conf.d/30-app.conf` on the VPS — Nginx will serve the
API alone. (Leaving it costs nothing: the frontend upstream is resolved per
request, so the block is inert when no frontend container exists.)

`NEXT_PUBLIC_*` values are inlined into the client bundle at build time, so
changing the API URL requires a rebuild, not just a restart.

## Sizing

Defaults suit a 2-core / 4GB VPS:

```
API_WORKERS=4          # (2 x cores) + 1, bounded by RAM
WORKER_CONCURRENCY=2   # PDF rendering is CPU-bound
```

Redis is capped at 256MB with `noeviction`: for a job queue, refusing new work
is correct where silently dropping queued reports is not.

---

## Three bugs that only showed up when this was actually run

Each broke the *default* deployment and none was visible from reading the
config.

**1. Nginx would not start without the frontend.** An `upstream` block names a
host, and Nginx resolves it once at startup and refuses to boot if it is
missing. With the frontend on Vercel — the documented default — the `frontend`
container does not exist, so Nginx died and took the API down with it. The app
host now uses a variable in `proxy_pass`, which defers resolution to request
time: Nginx starts either way and simply 502s if no frontend is deployed here.

**2. Certificates could never be issued on a first deploy.** `init-certs.sh`
starts Nginx to serve the ACME challenge, but Nginx will not start when an
`ssl_certificate` file is missing — and on a fresh box none exist. There is no
ordering that resolves it. The script now writes throwaway self-signed
certificates first so Nginx can boot; certbot overwrites them with
`--force-renewal`.

**3. `beat` was permanently unhealthy.** It inherited the image's HTTP health
check, but a scheduler serves no HTTP, so the probe could never pass. A service
stuck on "unhealthy" is worse than no check, because it trains you to ignore
the column. It now checks its own pidfile.

Verified from an empty slate — no volumes, no database, no certificates — that
all six migrations apply, every service reaches healthy, and a shop can sign
up, open a till, ring up a sale and export a report through Nginx over TLS.

---

## Payment gateways

Stripe does not operate in Uzbekistan. Payme and Click do, and they invert the
usual integration: instead of us creating a session and receiving a webhook,
**the gateway calls us** and drives the transaction.

Register these callback URLs in each provider's merchant cabinet:

| Provider | URL |
|---|---|
| Payme | `https://api.<domain>/api/v1/billing/payme` |
| Click — Prepare | `https://api.<domain>/api/v1/billing/click/prepare` |
| Click — Complete | `https://api.<domain>/api/v1/billing/click/complete` |

Then fill the credentials in `.env` and `docker compose up -d api`.

These are the only unauthenticated write endpoints in the system, and they
have to be — the caller is a gateway with no session. Authentication is the
provider's own scheme, checked inside the adapter before anything is written:
HTTP Basic `Paycom:<key>` for Payme, an MD5 signature over a fixed field order
for Click. Both are verified before a single row is touched.

Leave a provider's credentials blank and its payment button simply does not
appear. A dead button is worse than none: the shop assumes their card failed
rather than that nobody wired up the provider.

**Payme always gets a 200**, errors included. It reads a non-200 as a
transport failure and retries forever, which turns a permanent rejection into
a loop.

### Dunning

`run_billing_cycle` runs daily at 02:30 UTC via Celery beat:

1. subscriptions past their period end get an invoice
2. invoices unpaid past `BILLING_GRACE_DAYS` (default 5) suspend the shop

In that order, so a shop is never suspended in the same run that first
invoiced it. Paying reopens a suspended shop immediately. Nothing is ever
deleted.

The task is idempotent — invoicing is keyed to the period — so a missed day
catches up rather than double-billing anyone.
