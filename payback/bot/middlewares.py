"""Bot middlewares: DB session, current user, logging, and error handling."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.bot import texts
from payback.db.repositories import ExpensesRepo, InvitesRepo, UsersRepo
from payback.services.people import PeopleService

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Log unexpected failures and tell the user something went wrong."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except SkipHandler:
            # Let aiogram continue to the next matching handler/router.
            raise
        except Exception:
            logger.exception(
                "unhandled bot error",
                extra={"telegram_user_id": _actor_telegram_id(event)},
            )
            await _notify_user(event, texts.GENERIC_ERROR)
            return None


class DbRepositoryMiddleware(BaseMiddleware):
    """Open a DB session per update, inject repos, and load the local user."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id = _actor_telegram_id(event)
        logger.info(
            "telegram update",
            extra={
                "telegram_user_id": telegram_id,
                "update_type": type(event).__name__,
            },
        )
        async with self.session_factory() as session:
            users_repo = UsersRepo(session)
            invites_repo = InvitesRepo(session)
            expenses_repo = ExpensesRepo(session)
            user = (
                await users_repo.get_by_telegram_id(telegram_id)
                if telegram_id is not None
                else None
            )
            data["users_repo"] = users_repo
            data["invites_repo"] = invites_repo
            data["expenses_repo"] = expenses_repo
            data["people"] = PeopleService(users_repo, invites_repo)
            data["session"] = session
            data["user"] = user

            if user is not None and not user.is_active:
                await _notify_user(event, texts.INACTIVE_USER)
                return None

            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result


def _actor_telegram_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message) and event.from_user is not None:
        return event.from_user.id
    if isinstance(event, CallbackQuery) and event.from_user is not None:
        return event.from_user.id
    return None


async def _notify_user(event: TelegramObject, text: str) -> None:
    try:
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
    except Exception:
        logger.exception("failed to notify user about a bot error")


__all__ = ["DbRepositoryMiddleware", "ErrorHandlingMiddleware"]
