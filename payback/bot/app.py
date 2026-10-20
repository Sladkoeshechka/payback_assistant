from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.bot import approval, commands, people, staff, submission
from payback.bot.middlewares import DbRepositoryMiddleware, ErrorHandlingMiddleware
from payback.config import Settings
from payback.planfix.directories import DirectoryCache
from payback.planfix.models import PlanfixSchema
from payback.services.ports import NotifierPort, PlanfixPort


def create_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    return bot


def create_dispatcher(
    settings: Settings,
    async_session: async_sessionmaker[AsyncSession],
    *,
    planfix: PlanfixPort | None = None,
    directory_cache: DirectoryCache | None = None,
    planfix_schema: PlanfixSchema | None = None,
    notifier: NotifierPort | None = None,
) -> Dispatcher:
    dp = Dispatcher(
        storage=MemoryStorage(),
        settings=settings,
        planfix=planfix,
        directory_cache=directory_cache,
        planfix_schema=planfix_schema,
        notifier=notifier,
    )
    # First registered = outermost: errors wrap the DB session middleware.
    dp.message.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())
    dp.message.middleware(DbRepositoryMiddleware(session_factory=async_session))
    dp.callback_query.middleware(DbRepositoryMiddleware(session_factory=async_session))
    dp.include_router(people.create_invite_router())
    dp.include_router(people.create_router())
    dp.include_router(staff.create_router())
    dp.include_router(approval.create_router())
    dp.include_router(submission.create_router())
    dp.include_router(commands.create_router())
    return dp
