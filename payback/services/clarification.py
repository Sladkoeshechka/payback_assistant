"""Employee replies while an expense is in clarification (stage 8B)."""

import logging

from payback.config import PlanfixStatusIds
from payback.db.models import Expense, ExpenseStatus, User
from payback.db.repositories.expenses import ExpensesRepo
from payback.services.planfix_text import attributed_comment
from payback.services.ports import NotifierPort, PlanfixPort

logger = logging.getLogger(__name__)


class ClarificationError(Exception):
    """Base class for clarification-reply failures."""


class NoClarificationPendingError(ClarificationError):
    """The employee has no expense waiting for a clarification reply."""


class ClarificationService:
    """Apply an employee's text/photo answer and return the expense to pending."""

    def __init__(
        self,
        expenses: ExpensesRepo,
        planfix: PlanfixPort,
        notifier: NotifierPort,
        status_ids: PlanfixStatusIds,
    ) -> None:
        self._expenses = expenses
        self._planfix = planfix
        self._notifier = notifier
        self._status_ids = status_ids

    async def reply(
        self,
        *,
        employee: User,
        manager: User | None,
        text: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str = "reply.jpg",
        image_content_type: str = "image/jpeg",
    ) -> Expense:
        if text is None and image_bytes is None:
            raise ValueError("clarification reply needs text or an image")
        expense = await self._expenses.get_clarification_for_employee(employee.id)
        if expense is None:
            raise NoClarificationPendingError(
                f"employee {employee.id} has no clarification expense"
            )

        await self._push_planfix(
            expense,
            employee=employee,
            text=text,
            image_bytes=image_bytes,
            image_filename=image_filename,
            image_content_type=image_content_type,
        )
        await self._expenses.set_status(expense, ExpenseStatus.PENDING)
        # Commit before Telegram notify so a send failure cannot undo PlanFix.
        await self._expenses.commit()
        if manager is not None:
            reply_for_manager = text if text is not None else "Ответ сотрудника (фото)"
            try:
                if expense.manager_message_id is not None:
                    await self._notifier.clear_manager_decision_keyboard(
                        manager=manager,
                        message_id=expense.manager_message_id,
                    )
                message_id = await self._notifier.notify_manager_expense_card(
                    manager=manager,
                    employee=employee,
                    expense=expense,
                    image_bytes=image_bytes,
                    reply_text=reply_for_manager,
                )
            except Exception:
                logger.exception(
                    "failed to re-notify manager after clarification reply",
                    extra={"expense_id": expense.id},
                )
            else:
                await self._expenses.set_manager_message(expense, message_id)
        return expense

    async def _push_planfix(
        self,
        expense: Expense,
        *,
        employee: User,
        text: str | None,
        image_bytes: bytes | None,
        image_filename: str,
        image_content_type: str,
    ) -> None:
        if expense.planfix_task_id is None:
            return
        task_id = expense.planfix_task_id
        if image_bytes is not None:
            file_id = await self._planfix.upload_file(
                image_bytes,
                filename=image_filename,
                content_type=image_content_type,
            )
            await self._planfix.attach_file(file_id, task_id)
        body = text if text is not None else "(фото)"
        await self._planfix.add_comment(task_id, attributed_comment(employee, body))
        await self._planfix.update_task(task_id, {"status": {"id": self._status_ids.pending}})


__all__ = [
    "ClarificationError",
    "ClarificationService",
    "NoClarificationPendingError",
]
