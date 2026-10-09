from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.bot.middlewares import DbRepositoryMiddleware
from payback.bot.people import create_invite_router, create_router
from payback.config import Settings


def create_bot(settings: Settings) -> Bot:
    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else None
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    return bot


def create_dispatcher(
    settings: Settings, async_session: async_sessionmaker[AsyncSession]
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), settings=settings)
    dp.message.middleware(DbRepositoryMiddleware(session_factory=async_session))
    dp.callback_query.middleware(DbRepositoryMiddleware(session_factory=async_session))
    dp.include_router(create_invite_router())
    dp.include_router(create_router())
    return dp
