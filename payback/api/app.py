"""FastAPI application factory (stage 9A/9B)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from payback import __version__
from payback.api.webhooks import create_router as create_webhook_router
from payback.config import Settings, get_settings


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Process lifespan placeholder.

    Stage 9E will start Planfix schema checks and aiogram polling here, and wait
    for background tasks on shutdown. Until then the API can be tested alone.
    """
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the HTTP app (health + PlanFix webhook intake)."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="payback", version=__version__, lifespan=_lifespan)
    app.state.webhook_secret = settings.webhook_secret.get_secret_value()
    # Testable sink for 9B; 9C will replace stub processing with real work.
    app.state.webhook_events = []
    app.include_router(create_webhook_router())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


__all__ = ["create_app"]
