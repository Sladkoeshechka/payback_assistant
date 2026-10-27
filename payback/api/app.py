"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback import __version__
from payback.api.webhooks import create_router as create_webhook_router
from payback.config import Settings, get_settings
from payback.services.ports import NotifierPort, PlanfixPort

logger = logging.getLogger(__name__)


def _on_polling_done(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        logger.exception("telegram polling crashed")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run aiogram polling with the HTTP app; clean up on uvicorn shutdown."""
    bot = getattr(app.state, "bot", None)
    dispatcher = getattr(app.state, "dispatcher", None)
    if bot is not None and dispatcher is not None:
        await bot.get_me()
        await bot.delete_webhook(drop_pending_updates=True)
        polling_task = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                handle_signals=False,
                close_bot_session=False,
            )
        )
        polling_task.add_done_callback(_on_polling_done)
        app.state.polling_task = polling_task
    try:
        yield
    finally:
        if dispatcher is not None:
            with suppress(RuntimeError):
                await dispatcher.stop_polling()
        current_polling_task = getattr(app.state, "polling_task", None)
        if current_polling_task is not None and not current_polling_task.done():
            current_polling_task.cancel()
            with suppress(asyncio.CancelledError):
                await current_polling_task
        live_planfix = getattr(app.state, "live_planfix_client", None)
        if live_planfix is not None:
            await live_planfix.aclose()
        if bot is not None:
            await bot.session.close()
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            await engine.dispose()
            app.state.engine = None


def create_app(
    settings: Settings | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    engine: AsyncEngine | None = None,
    planfix: PlanfixPort | None = None,
    notifier: NotifierPort | None = None,
    bot: Any | None = None,
    dispatcher: Any | None = None,
    live_planfix_client: Any | None = None,
) -> FastAPI:
    """Build the HTTP app (health + PlanFix webhook intake)."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(title="payback", version=__version__, lifespan=_lifespan)
    app.state.webhook_secret = settings.webhook_secret.get_secret_value()
    # Testable sink for webhook intake; processing still appends here when configured.
    app.state.webhook_events = []
    app.state.session_factory = session_factory
    app.state.engine = engine
    app.state.planfix = planfix
    app.state.notifier = notifier
    app.state.status_ids = settings.planfix.statuses
    app.state.bot = bot
    app.state.dispatcher = dispatcher
    app.state.live_planfix_client = live_planfix_client
    app.state.polling_task = None
    app.include_router(create_webhook_router())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


__all__ = ["create_app"]
