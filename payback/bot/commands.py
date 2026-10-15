"""Telegram handlers for ``/help``, ``/refresh``, ``/my``, and ``/pending``."""

from datetime import UTC, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from payback.bot import texts
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.planfix.directories import DirectoryCache
from payback.services.people import (
    EmployeeRequiredError,
    ManagerRequiredError,
    PeopleService,
)

_MY_EXPENSES_WINDOW = timedelta(days=30)


def create_router() -> Router:
    router = Router()

    @router.message(Command("help"))
    async def cmd_help(message: Message, users_repo: UsersRepo) -> None:
        if message.from_user is None:
            return
        user = await users_repo.get_by_telegram_id(message.from_user.id)
        role = user.role if user is not None and user.is_active else None
        await message.answer(texts.help_text(role))

    @router.message(Command("refresh"))
    async def cmd_refresh(
        message: Message,
        people: PeopleService,
        directory_cache: DirectoryCache | None = None,
    ) -> None:
        if message.from_user is None:
            return
        try:
            await people.verify_manager(message.from_user.id)
        except ManagerRequiredError:
            await message.answer(texts.MANAGER_ONLY)
            return
        if directory_cache is None:
            await message.answer(texts.REFRESH_UNAVAILABLE)
            return
        directory_cache.invalidate()
        await message.answer(texts.REFRESH_DONE)

    @router.message(Command("my"))
    async def cmd_my(message: Message, people: PeopleService, expenses_repo: ExpensesRepo) -> None:
        if message.from_user is None:
            return
        try:
            employee = await people.verify_employee(message.from_user.id)
        except EmployeeRequiredError:
            await message.answer(texts.EMPLOYEE_ONLY)
            return
        since = datetime.now(UTC) - _MY_EXPENSES_WINDOW
        expenses = await expenses_repo.list_for_employee_since(employee.id, since)
        if not expenses:
            await message.answer(texts.NO_EXPENSES)
            return
        await message.answer(texts.my_expenses(expenses))

    @router.message(Command("pending"))
    async def cmd_pending(
        message: Message, people: PeopleService, expenses_repo: ExpensesRepo
    ) -> None:
        if message.from_user is None:
            return
        try:
            manager = await people.verify_manager(message.from_user.id)
        except ManagerRequiredError:
            await message.answer(texts.MANAGER_ONLY)
            return
        expenses = await expenses_repo.list_pending_for_manager(manager.id)
        if not expenses:
            await message.answer(texts.NO_PENDING)
            return
        await message.answer(texts.pending_expenses(expenses))

    return router


__all__ = ["create_router"]
