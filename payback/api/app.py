"""FastAPI application factory (stage 9A/9B/9C)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback import __version__
from payback.api.webhooks import create_router as create_webhook_router
from payback.config import Settings, get_settings
from payback.services.ports import NotifierPort, PlanfixPort


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Process lifespan placeholder.

    Stage 9E will start PlanFix schema checks and aiogram polling here, and wait
    for background tasks on shutdown. Until then the API can be tested alone.
    """
    yield


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    planfix: PlanfixPort | None = None,
    notifier: NotifierPort | None = None,
) -> FastAPI:
    """Build the HTTP app (health + PlanFix webhook intake)."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="payback", version=__version__, lifespan=_lifespan)
    app.state.webhook_secret = settings.webhook_secret.get_secret_value()
    # Testable sink for 9B; processing still appends here when configured.
    app.state.webhook_events = []
    app.state.session_factory = session_factory
    app.state.planfix = planfix
    app.state.notifier = notifier
    app.state.status_ids = settings.planfix.statuses
    app.include_router(create_webhook_router())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


__all__ = ["create_app"]
