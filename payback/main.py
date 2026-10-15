"""Entry point.

For now it loads settings, sets up logging and reports what it found. The Planfix
schema check arrives with the API client (docs/plan.md §4) and the FastAPI app plus
the aiogram polling task arrive with the webhooks (§9) — until then this must not
pretend to start a bot.
"""

import asyncio
import logging
import sys

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from payback import __version__
from payback.bot.app import create_bot, create_dispatcher
from payback.config import Settings, get_settings
from payback.db.base import Base
from payback.db.session import build_engine
from payback.logging_setup import configure_logging, redact
from payback.planfix.client import PlanfixClient
from payback.planfix.directories import DirectoryCache

logger = logging.getLogger(__name__)

EXIT_BAD_CONFIG = 2


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

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    bot = create_bot(settings)
    planfix = PlanfixClient(settings.planfix)
    directory_cache = DirectoryCache(planfix)
    dp = create_dispatcher(
        settings,
        session_factory,
        planfix=planfix,
        directory_cache=directory_cache,
    )

    try:
        me = await bot.get_me()
        logger.info("Бот подключен: @%s (id=%s)", me.username, me.id)
    except Exception:
        logger.exception("He удалось подключиться к Telegram. Проверьте конфигурацию.")
        return 1

    # Ha всякий случай чистим вебхуки перед стартом пуллинга
    await bot.delete_webhook(drop_pending_updates=True)

    # 4. Запускаем бесконечный цикл пуллинга (блокирующий вызов)
    try:
        logger.info("Пуллинг Telegram запущен")
        await dp.start_polling(bot)
    finally:
        # Корректное закрытие ресурсов при остановке (Ctrl+C / docker stop)
        await planfix.aclose()
        await bot.session.close()
        logger.info("Бот остановлен")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
