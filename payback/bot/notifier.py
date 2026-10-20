"""Telegram implementation of manager and employee notifications."""


import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from payback.bot import texts
from payback.bot.keyboards import manager_decision_keyboard
from payback.db.models import Expense, ExpenseStatus, User

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send expense cards and decision updates over Telegram."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def notify_manager_new_expense(
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

    async def clear_manager_decision_keyboard(
        self, *, manager: User, message_id: int
    ) -> None:
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

    async def notify_employee_decision(
        self,
        *,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        task_id = expense.planfix_task_id if expense.planfix_task_id is not None else expense.id
        if expense.status is ExpenseStatus.APPROVED:
            text = texts.EMPLOYEE_APPROVED.format(task_id=task_id)
        elif expense.status is ExpenseStatus.REJECTED:
            text = texts.EMPLOYEE_REJECTED.format(task_id=task_id, detail=detail or "—")
        elif expense.status is ExpenseStatus.CLARIFICATION:
            text = texts.EMPLOYEE_CLARIFICATION.format(task_id=task_id, detail=detail or "—")
        else:
            text = f"Статус заявки №{task_id}: {texts.status_label(expense.status)}"
        await self._bot.send_message(chat_id=employee.telegram_id, text=text)


__all__ = ["TelegramNotifier"]
