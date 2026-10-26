"""Process entry point: FastAPI + aiogram polling in one event loop (stage 9E)."""

import asyncio
import logging
import sys
from typing import Any

import uvicorn
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from payback import __version__
from payback.api import create_app
from payback.bot.app import create_bot, create_dispatcher
from payback.bot.notifier import TelegramNotifier
from payback.config import Settings, get_settings
from payback.db.base import Base
from payback.db.session import build_engine
from payback.logging_setup import configure_logging, redact
from payback.planfix.client import PlanfixClient
from payback.planfix.directories import DirectoryCache
from payback.planfix.exceptions import PlanfixSchemaError
from payback.planfix.models import PlanfixDirectoryEntry, PlanfixSchema
from payback.planfix.schema import validate_planfix_schema
from payback.services.fakes import FakePlanfix
from payback.services.ports import PlanfixPort

logger = logging.getLogger(__name__)

EXIT_BAD_CONFIG = 2
EXIT_SIGINT = 130

# Stable fake directory ids for offline DEV_MODE (no live Planfix).
_DEV_CATEGORY_DIRECTORY_ID = 9001
_DEV_DIRECTION_DIRECTORY_ID = 9002


def format_config_errors(error: ValidationError) -> str:
    """Render a settings failure as the environment variables to go and fix.

    A raw pydantic traceback is the wrong thing to greet an operator with; spec §8
    asks the service to refuse to start and say what is missing.
    """
    lines = ["payback cannot start: the environment is incomplete or invalid"]
    for item in error.errors():
        # Nested models report their explicit alias (PLANFIX_FIELD_AMOUNT); top-level
        # fields report the field name, whose variable is the uppercase form. Errors
        # from a model-wide validator have no location at all.
        location = ".".join(str(part) for part in item["loc"]).upper() or "(whole config)"
        lines.append(f"  {location}: {item['msg']}")
    lines.append("See .env.example for every variable and what it means.")
    return "\n".join(lines)


def describe(settings: Settings) -> dict[str, object]:
    """Non-secret startup facts worth having in the log."""
    return {
        "version": __version__,
        "planfix_account": settings.planfix.account,
        "planfix_object_id": settings.planfix.object_id,
        "database": settings.database_url.split("://", 1)[0],
        "dev_mode": settings.dev_mode,
        "allow_no_receipt": settings.allow_no_receipt,
        "max_amount": str(settings.max_amount),
        "max_receipt_age_days": settings.max_receipt_age_days,
        "proxy": settings.proxy_url is not None,
    }


def offline_planfix_stack() -> tuple[FakePlanfix, PlanfixSchema]:
    """In-memory Planfix stand-in with sample directories for local Telegram tests."""
    planfix = FakePlanfix(
        directory_entries={
            _DEV_CATEGORY_DIRECTORY_ID: [
                PlanfixDirectoryEntry(key=1, name="Материалы"),
                PlanfixDirectoryEntry(key=2, name="Транспорт"),
                PlanfixDirectoryEntry(key=3, name="Прочее"),
            ],
            _DEV_DIRECTION_DIRECTORY_ID: [
                PlanfixDirectoryEntry(key=1, name="Офис"),
                PlanfixDirectoryEntry(key=2, name="Объект"),
            ],
        }
    )
    schema = PlanfixSchema(
        category_directory_id=_DEV_CATEGORY_DIRECTORY_ID,
        direction_directory_id=_DEV_DIRECTION_DIRECTORY_ID,
    )
    return planfix, schema


async def connect_planfix(
    settings: Settings,
) -> tuple[PlanfixPort, PlanfixSchema, Any | None]:
    """Return a live Planfix client, or an offline fake when ``DEV_MODE`` allows it.

    The third value is the live ``PlanfixClient`` to close on shutdown, if any.
    """
    client = PlanfixClient(settings.planfix)
    try:
        schema = await validate_planfix_schema(client, settings.planfix)
    except PlanfixSchemaError:
        await client.aclose()
        # Configuration/schema mismatch must fail startup (stage 10 A3).
        raise
    except Exception:
        await client.aclose()
        if not settings.dev_mode:
            raise
        logger.warning(
            "Planfix unavailable; DEV_MODE uses FakePlanfix with sample directories",
            exc_info=True,
        )
        fake, schema = offline_planfix_stack()
        return fake, schema, None
    return client, schema, client


async def main() -> int:
    try:
        settings = get_settings()
    except ValidationError as error:
        # Logging is not configured yet, and a half-read config must not be trusted
        # to tell us where to log, so this one message goes straight to stderr.
        print(format_config_errors(error), file=sys.stderr)
        return EXIT_BAD_CONFIG

    configure_logging(settings.log_level)
    redact(*settings.secrets())

    logger.info("payback starting", extra=describe(settings))

    engine = build_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    except Exception:
        await engine.dispose()
        raise

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    bot = create_bot(settings)
    try:
        planfix, planfix_schema, live_client = await connect_planfix(settings)
    except Exception:
        logger.exception("Planfix schema validation failed")
        await bot.session.close()
        await engine.dispose()
        return 1

    directory_cache = DirectoryCache(planfix)
    notifier = TelegramNotifier(bot)
    dispatcher = create_dispatcher(
        settings,
        session_factory,
        planfix=planfix,
        directory_cache=directory_cache,
        planfix_schema=planfix_schema,
        notifier=notifier,
    )
    app = create_app(
        settings,
        session_factory=session_factory,
        engine=engine,
        planfix=planfix,
        notifier=notifier,
        bot=bot,
        dispatcher=dispatcher,
        live_planfix_client=live_client,
    )
    # Lifespan owns engine/bot/planfix teardown while the server is running.
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_config=None,
        )
    )
    try:
        await server.serve()
    except asyncio.CancelledError:
        # SIGINT replay after uvicorn's graceful lifespan shutdown — normal stop.
        return 0
    if not server.started:
        await engine.dispose()
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(EXIT_SIGINT) from None
