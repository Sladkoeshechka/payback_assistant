"""Telegram implementation of manager notifications."""

from aiogram import Bot
from aiogram.types import BufferedInputFile

from payback.bot import texts
from payback.bot.keyboards import manager_decision_keyboard
from payback.db.models import Expense, User


class TelegramNotifier:
    """Send expense cards to managers over Telegram."""

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


__all__ = ["TelegramNotifier"]
