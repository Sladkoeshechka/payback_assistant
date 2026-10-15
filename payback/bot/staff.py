"""Telegram handlers for ``/staff`` and related callbacks."""

import logging
from typing import Protocol

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from payback.bot import texts
from payback.bot.keyboards import planfix_users_keyboard, staff_keyboard
from payback.planfix.exceptions import PlanfixError
from payback.planfix.models import PlanfixUser
from payback.services.people import (
    InviteNotFoundError,
    ManagerRequiredError,
    PeopleService,
    PlanfixLinkConflictError,
    StaffMemberNotFoundError,
    StaffOverview,
)

logger = logging.getLogger(__name__)


class PlanfixUsersPort(Protocol):
    """Minimal Planfix surface needed to link a manager account."""

    async def list_users(self) -> list[PlanfixUser]: ...


def create_router() -> Router:
    router = Router()

    @router.message(Command("staff"))
    async def cmd_staff(message: Message, people: PeopleService) -> None:
        if message.from_user is None:
            return
        try:
            overview = await people.get_staff_overview(message.from_user.id)
        except ManagerRequiredError:
            await message.answer(texts.MANAGER_ONLY)
            return
        await message.answer(
            texts.staff_overview(overview),
            reply_markup=staff_keyboard(overview),
        )

    @router.callback_query(F.data == "staff:link")
    async def start_planfix_link(
        callback: CallbackQuery,
        people: PeopleService,
        planfix: PlanfixUsersPort | None = None,
    ) -> None:
        if callback.from_user is None or not isinstance(callback.message, Message):
            return
        try:
            await people.verify_manager(callback.from_user.id)
        except ManagerRequiredError:
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        if planfix is None:
            await callback.answer(texts.PLANFIX_UNAVAILABLE, show_alert=True)
            return
        try:
            users = await planfix.list_users()
        except PlanfixError:
            logger.exception("failed to list Planfix users for linking")
            await callback.answer(texts.PLANFIX_UNAVAILABLE, show_alert=True)
            return
        if not users:
            await callback.answer(texts.PLANFIX_USERS_EMPTY, show_alert=True)
            return
        await callback.message.answer(
            texts.CHOOSE_PLANFIX_USER,
            reply_markup=planfix_users_keyboard(users),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("staff:pf:"))
    async def choose_planfix_user(callback: CallbackQuery, people: PeopleService) -> None:
        if callback.from_user is None or callback.data is None or callback.message is None:
            return
        planfix_user_id = int(callback.data.rsplit(":", 1)[1])
        try:
            manager = await people.link_planfix_user(callback.from_user.id, planfix_user_id)
        except ManagerRequiredError:
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        except PlanfixLinkConflictError:
            await callback.answer(texts.PLANFIX_LINK_CONFLICT, show_alert=True)
            return
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                texts.PLANFIX_LINKED.format(planfix_user_id=manager.planfix_user_id)
            )
        await callback.answer()

    @router.callback_query(F.data == "staff:cancel")
    async def cancel_planfix_link(callback: CallbackQuery) -> None:
        if isinstance(callback.message, Message):
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")

    @router.callback_query(F.data.startswith("staff:revoke:"))
    async def revoke_invite(callback: CallbackQuery, people: PeopleService) -> None:
        if callback.from_user is None or callback.data is None or callback.message is None:
            return
        invite_id = int(callback.data.rsplit(":", 1)[1])
        try:
            await people.revoke_invite(callback.from_user.id, invite_id)
            overview = await people.get_staff_overview(callback.from_user.id)
        except ManagerRequiredError:
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        except InviteNotFoundError:
            await callback.answer(texts.STAFF_ACTION_UNAVAILABLE, show_alert=True)
            return
        await _refresh_staff_message(callback, overview)
        await callback.answer(texts.INVITE_REVOKED)

    @router.callback_query(F.data.startswith("staff:off:"))
    async def deactivate_employee(callback: CallbackQuery, people: PeopleService) -> None:
        if callback.from_user is None or callback.data is None or callback.message is None:
            return
        employee_id = int(callback.data.rsplit(":", 1)[1])
        try:
            employee = await people.deactivate_subordinate(callback.from_user.id, employee_id)
            overview = await people.get_staff_overview(callback.from_user.id)
        except ManagerRequiredError:
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        except StaffMemberNotFoundError:
            await callback.answer(texts.STAFF_ACTION_UNAVAILABLE, show_alert=True)
            return
        await _refresh_staff_message(callback, overview)
        await callback.answer(
            texts.EMPLOYEE_DEACTIVATED.format(full_name=texts.full_name(employee))
        )

    return router


async def _refresh_staff_message(callback: CallbackQuery, overview: StaffOverview) -> None:
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_text(
        texts.staff_overview(overview),
        reply_markup=staff_keyboard(overview),
    )


__all__ = ["PlanfixUsersPort", "create_router"]
