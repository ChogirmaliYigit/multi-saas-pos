# Multi-tenant SaaS Point of Sale

<!--
  Static "built with" badges only. There is deliberately no build or coverage
  badge here: without a CI workflow behind it, a green "passing" shield asserts
  something nobody is checking, and it stays green after the day it stops being
  true. Add a workflow first, then add the badge that reports it.
-->

[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

Next.js frontend, FastAPI backend, PostgreSQL with row-level tenant isolation.

**104 backend tests**, run against real PostgreSQL, Redis and Celery rather
than mocks — including the concurrency case where two tills race for the last
unit of stock, and database-level assertions that one shop cannot read
another's rows.

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
| `deployment/VERCEL.md` | Frontend on Vercel: settings, env, domains |

## Commands

`make help` lists everything. The common ones:

```bash
make check      # lint + typecheck + tests
make up         # run the production stack locally
make deploy     # build, migrate, roll out, roll back on failure
```
