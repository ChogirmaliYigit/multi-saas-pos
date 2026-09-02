# syntax=docker/dockerfile:1.7
#
# Multi-stage so the runtime image carries no compiler toolchain. The build
# stage needs gcc for asyncpg and argon2-cffi wheels; shipping that to a VPS
# would add ~300MB and a pile of CVEs for nothing.

# --------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# A venv rather than --user: it copies to the runtime stage as one directory
# and keeps the app's dependencies off the system Python.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -r requirements.txt


# --------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# libpq5 only -- the client library, not the -dev headers.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root. A container that runs as root turns a code-execution bug into a
# host-level one the moment anything escapes.
RUN groupadd --system --gid 1001 pos \
    && useradd --system --uid 1001 --gid pos --create-home pos

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=pos:pos . .

# Report exports land here; the compose file mounts a volume over it so files
# survive a redeploy.
RUN mkdir -p /var/lib/pos/reports && chown -R pos:pos /var/lib/pos

USER pos
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Gunicorn supervises uvicorn workers: it handles worker restarts and graceful
# shutdown, which bare uvicorn does not. Worker count is set in compose, since
# it depends on the VPS's core count rather than the image.
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
