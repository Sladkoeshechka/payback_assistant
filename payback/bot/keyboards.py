"""Inline keyboards for people-management and expense-submission flows."""

# ruff: noqa: RUF001

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from payback.db.models import Invite, User, UserRole
from payback.planfix.models import PlanfixDirectoryEntry, PlanfixUser
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
        name = f"{employee.first_name} {employee.last_name}"
        if employee.is_active:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Отключить: {name}",
                        callback_data=f"staff:off:{employee.id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Включить: {name}",
                        callback_data=f"staff:on:{employee.id}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Передать: {name}",
                    callback_data=f"staff:xfer:{employee.id}",
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


def transfer_managers_keyboard(
    employee_id: int, managers: list[User]
) -> InlineKeyboardMarkup:
    """Pick which manager receives the subordinate."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{manager.first_name} {manager.last_name}",
                callback_data=f"staff:xferto:{employee_id}:{manager.id}",
            )
        ]
        for manager in managers
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="staff:cancel")])
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


def qr_missing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Переснять", callback_data="sub:retry")],
            [InlineKeyboardButton(text="Ввести вручную", callback_data="sub:manual")],
        ]
    )


def directory_keyboard(
    entries: list[PlanfixDirectoryEntry] | tuple[PlanfixDirectoryEntry, ...],
    *,
    prefix: str,
    include_none: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=entry.name, callback_data=f"{prefix}:{entry.key}")]
        for entry in entries
    ]
    if include_none:
        rows.append([InlineKeyboardButton(text="Без направления", callback_data=f"{prefix}:none")])
    rows.append([InlineKeyboardButton(text="Отменить", callback_data="sub:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_comment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить", callback_data="sub:skip_comment")],
            [InlineKeyboardButton(text="Отменить", callback_data="sub:cancel")],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Отправить", callback_data="sub:send"),
                InlineKeyboardButton(text="Исправить", callback_data="sub:edit"),
            ],
            [InlineKeyboardButton(text="Отменить", callback_data="sub:cancel")],
        ]
    )


def edit_field_keyboard(*, qr_locked: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not qr_locked:
        rows.append(
            [
                InlineKeyboardButton(text="Сумма", callback_data="sub:edit:amount"),
                InlineKeyboardButton(text="Дата", callback_data="sub:edit:date"),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(text="Категория", callback_data="sub:edit:category"),
                InlineKeyboardButton(text="Направление", callback_data="sub:edit:direction"),
            ],
            [InlineKeyboardButton(text="Комментарий", callback_data="sub:edit:comment")],
            [InlineKeyboardButton(text="Назад", callback_data="sub:edit:back")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def replace_draft_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, начать новую", callback_data="sub:replace:yes"),
                InlineKeyboardButton(text="Нет", callback_data="sub:replace:no"),
            ]
        ]
    )


def proof_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отправить фото", callback_data="sub:proof:wait")],
            [InlineKeyboardButton(text="Пропустить", callback_data="sub:proof:skip")],
            [InlineKeyboardButton(text="Отменить", callback_data="sub:cancel")],
        ]
    )


def manager_decision_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    """Approve / reject / clarification buttons for a pending expense."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"mgr:approve:{expense_id}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"mgr:reject:{expense_id}"),
            ],
            [InlineKeyboardButton(text="Вопрос", callback_data=f"mgr:ask:{expense_id}")],
        ]
    )


def _invite_button_label(invite: Invite) -> str:
    role = "сотрудник" if invite.role == UserRole.EMPLOYEE else "руководитель"
    return f"{role} #{invite.id}"


def _planfix_user_label(user: PlanfixUser) -> str:
    name = " ".join(part for part in (user.name, user.last_name) if part).strip() or f"id {user.id}"
    return f"{name} (#{user.id})"


__all__ = [
    "confirm_keyboard",
    "directory_keyboard",
    "edit_field_keyboard",
    "invite_role_keyboard",
    "manager_decision_keyboard",
    "planfix_users_keyboard",
    "proof_photo_keyboard",
    "qr_missing_keyboard",
    "replace_draft_keyboard",
    "skip_comment_keyboard",
    "staff_keyboard",
    "transfer_managers_keyboard",
]
