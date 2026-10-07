"""Inline keyboards for people-management flows."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def invite_role_keyboard() -> InlineKeyboardMarkup:
    """Offer the two roles that a manager can invite."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сотрудника", callback_data="invite:employee")],
            [InlineKeyboardButton(text="Руководителя", callback_data="invite:manager")],
        ]
    )


__all__ = ["invite_role_keyboard"]
