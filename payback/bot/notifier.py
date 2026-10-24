"""Telegram adapter for ``NotifierPort`` (stage 8C)."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from payback.bot import texts
from payback.bot.keyboards import manager_decision_keyboard
from payback.db.models import Expense, User
from payback.services.notifications import format_employee_decision

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send expense cards and decision updates over Telegram."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_manager_expense_card(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
        image_bytes: bytes | None,
    ) -> int:
        caption = texts.manager_expense_card(employee=employee, expense=expense)
        markup = manager_decision_keyboard(expense.id)
        if image_bytes is not None:
            message = await self._bot.send_photo(
                chat_id=manager.telegram_id,
                photo=BufferedInputFile(image_bytes, filename="receipt.jpg"),
                caption=caption,
                reply_markup=markup,
            )
        else:
            message = await self._bot.send_message(
                chat_id=manager.telegram_id,
                text=caption,
                reply_markup=markup,
            )
        return message.message_id

    async def clear_manager_decision_keyboard(self, *, manager: User, message_id: int) -> None:
        try:
            await self._bot.edit_message_reply_markup(
                chat_id=manager.telegram_id,
                message_id=message_id,
                reply_markup=None,
            )
        except TelegramAPIError:
            logger.exception(
                "failed to clear manager decision keyboard",
                extra={"manager_telegram_id": manager.telegram_id, "message_id": message_id},
            )

    async def mark_manager_decision_in_planfix(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
    ) -> None:
        if expense.manager_message_id is None:
            return
        body = texts.manager_expense_card(employee=employee, expense=expense)
        text = f"{body}\n\n{texts.DECISION_IN_PLANFIX}"
        chat_id = manager.telegram_id
        message_id = expense.manager_message_id
        try:
            if expense.telegram_file_id is not None:
                await self._bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=text,
                    reply_markup=None,
                )
            else:
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=None,
                )
        except TelegramAPIError:
            logger.exception(
                "failed to mark manager card decided in PlanFix",
                extra={"manager_telegram_id": chat_id, "message_id": message_id},
            )
            await self.clear_manager_decision_keyboard(manager=manager, message_id=message_id)

    async def notify_employee_decision(
        self,
        *,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        text = format_employee_decision(expense=expense, detail=detail)
        try:
            await self._bot.send_message(chat_id=employee.telegram_id, text=text)
        except TelegramAPIError:
            logger.exception(
                "failed to notify employee of decision",
                extra={
                    "employee_telegram_id": employee.telegram_id,
                    "expense_id": expense.id,
                    "status": expense.status.value,
                },
            )


__all__ = ["TelegramNotifier"]
