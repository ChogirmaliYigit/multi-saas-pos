# Multi-tenant SaaS Point of Sale

Next.js frontend, FastAPI backend, PostgreSQL with row-level tenant isolation.

```
frontend/     Next.js 16 · React 19 · Tailwind 4 · shadcn/ui   (Vercel)
backend/      FastAPI · SQLAlchemy 2 · Celery · PostgreSQL 16  (VPS, Docker)
deployment/   Nginx, TLS, deploy and backup scripts
```

## Quick start

```bash
make dev-db                       # Postgres + Redis
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp backend/.env.example backend/.env    # set SECRET_KEY
make migrate seed
make api                          # http://localhost:8000/docs

cd frontend && npm install
cp .env.local.example .env.local
make web                          # http://localhost:3000
```

Then sign up at `/signup`, and `make seed-demo SLUG=<your-slug>` for a catalog.

## Tenant isolation

Every shop's data is separated three times over:

1. **Middleware** — the tenant comes from the verified JWT, never a header,
   body or subdomain.
2. **ORM filter** — a session-level hook appends `WHERE tenant_id = …` to every
   query against a tenant-owned model, so a handler that forgets cannot leak.
3. **PostgreSQL RLS** — the app connects as an unprivileged role under
   `FORCE ROW LEVEL SECURITY`, with the tenant bound per transaction. This is
   the layer that holds when the other two have bugs.

`backend/docs/schema.md` explains the design and the decisions behind it.

## Documentation

| Doc | Covers |
|---|---|
| `backend/docs/schema.md` | Data model, isolation, POS/admin/platform internals |
| `frontend/docs/architecture.md` | Token storage, route groups, chart palette |
| `deployment/README.md` | VPS setup, certificates, deploys, backups |

## Commands

`make help` lists everything. The common ones:

```bash
make check      # lint + typecheck + tests
make up         # run the production stack locally
make deploy     # build, migrate, roll out, roll back on failure
```
