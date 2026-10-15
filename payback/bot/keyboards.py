"""Inline keyboards for people-management flows."""

# ruff: noqa: RUF001

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from payback.db.models import Invite, UserRole
from payback.planfix.models import PlanfixUser
from payback.services.people import StaffOverview


def invite_role_keyboard() -> InlineKeyboardMarkup:
    """Offer the two roles that a manager can invite."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сотрудника", callback_data="invite:employee")],
            [InlineKeyboardButton(text="Руководителя", callback_data="invite:manager")],
        ]
    )


def staff_keyboard(overview: StaffOverview) -> InlineKeyboardMarkup:
    """Actions for subordinates, unused invites, and Planfix linking."""
    rows: list[list[InlineKeyboardButton]] = []
    for employee in overview.subordinates:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Отключить: {employee.first_name} {employee.last_name}",
                    callback_data=f"staff:off:{employee.id}",
                )
            ]
        )
    for invite in overview.invites:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Отозвать: {_invite_button_label(invite)}",
                    callback_data=f"staff:revoke:{invite.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Связать с ПланФиксом", callback_data="staff:link")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def planfix_users_keyboard(users: list[PlanfixUser]) -> InlineKeyboardMarkup:
    """Let the manager pick which Planfix account is theirs."""
    rows = [
        [
            InlineKeyboardButton(
                text=_planfix_user_label(user),
                callback_data=f"staff:pf:{user.id}",
            )
        ]
        for user in users
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="staff:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _invite_button_label(invite: Invite) -> str:
    role = "сотрудник" if invite.role == UserRole.EMPLOYEE else "руководитель"
    return f"{role} #{invite.id}"


def _planfix_user_label(user: PlanfixUser) -> str:
    name = " ".join(part for part in (user.name, user.last_name) if part).strip() or f"id {user.id}"
    return f"{name} (#{user.id})"


__all__ = ["invite_role_keyboard", "planfix_users_keyboard", "staff_keyboard"]
