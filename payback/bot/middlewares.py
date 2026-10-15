from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.db.repositories import ExpensesRepo, InvitesRepo, UsersRepo
from payback.services.people import PeopleService


class DbRepositoryMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            users_repo = UsersRepo(session)
            invites_repo = InvitesRepo(session)
            expenses_repo = ExpensesRepo(session)
            data["users_repo"] = users_repo
            data["invites_repo"] = invites_repo
            data["expenses_repo"] = expenses_repo
            data["people"] = PeopleService(users_repo, invites_repo)
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result
