"""Telegram handlers for menu commands and DEV_MODE role switching."""

from datetime import UTC, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from payback.bot import texts
from payback.config import Settings
from payback.db.models import User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.planfix.directories import DirectoryCache
from payback.services.people import (
    EmployeeRequiredError,
    ManagerRequiredError,
    NotRegisteredError,
    PeopleService,
)

_MY_EXPENSES_WINDOW = timedelta(days=30)


def create_router() -> Router:
    router = Router()

    @router.message(Command("help"))
    async def cmd_help(message: Message, settings: Settings, user: User | None) -> None:
        role = user.role if user is not None else None
        await message.answer(
            texts.help_text(
                role,
                dev_mode=settings.dev_mode,
                allow_no_receipt=settings.allow_no_receipt,
            )
        )

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

    @router.message(Command("as"))
    async def cmd_as(
        message: Message,
        command: CommandObject,
        settings: Settings,
        people: PeopleService,
    ) -> None:
        """Switch role for one-account manual testing when ``DEV_MODE`` is on."""
        if not settings.dev_mode or message.from_user is None:
            return
        raw = (command.args or "").strip().lower()
        if raw not in {UserRole.EMPLOYEE.value, UserRole.MANAGER.value}:
            await message.answer(texts.DEV_AS_USAGE)
            return
        try:
            user = await people.switch_dev_role(message.from_user.id, UserRole(raw))
        except NotRegisteredError:
            await message.answer(texts.DEV_AS_NEED_REGISTER)
            return
        await message.answer(
            texts.DEV_AS_SWITCHED.format(
                role=texts.role_name(user.role),
                menu=texts.menu(user.role, allow_no_receipt=settings.allow_no_receipt),
            )
        )

    return router


__all__ = ["create_router"]
