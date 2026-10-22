"""FastAPI application factory (stage 9A)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payback import __version__


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Process lifespan placeholder.

    Stage 9E will start Planfix schema checks and aiogram polling here, and wait
    for background tasks on shutdown. Until then the API can be tested alone.
    """
    yield


def create_app() -> FastAPI:
    """Build the HTTP app (health now; PlanFix webhooks in 9B+)."""
    app = FastAPI(title="payback", version=__version__, lifespan=_lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


__all__ = ["create_app"]
