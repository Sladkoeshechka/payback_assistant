# Stage 11 step 1: production image (app + polling). Caddy comes in step 2.
# Python version matches local/dev (docs/plan.md §13).
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
COPY docs/spec.md docs/spec.md
COPY payback payback/
COPY alembic alembic/
COPY alembic.ini ./

# Runtime image installs libzbar; the zbar extra adds the Python binding.
RUN uv sync --frozen --no-dev --extra zbar --no-editable

FROM python:3.14-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libzbar0 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system payback \
    && useradd --system --gid payback --home-dir /app --shell /usr/sbin/nologin payback

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/payback /app/payback
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY docker/entrypoint.sh /app/docker/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN chmod +x /app/docker/entrypoint.sh \
    && chown -R payback:payback /app

USER payback

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
