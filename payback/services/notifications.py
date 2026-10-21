"""Outbound notification contract and employee message bodies (no aiogram)."""

# ruff: noqa: RUF001

from typing import Protocol

from payback.db.models import Expense, ExpenseStatus, User

NOTIFY_EMPLOYEE_APPROVED = "Заявка №{task_id} одобрена."
NOTIFY_EMPLOYEE_REJECTED = "Заявка №{task_id} отклонена.\nПричина: {detail}"
NOTIFY_EMPLOYEE_CLARIFICATION = "По заявке №{task_id} нужен ответ.\nВопрос: {detail}"

_STATUS_LABELS = {
    ExpenseStatus.PENDING_SUBMISSION: "Ожидает отправки",
    ExpenseStatus.PENDING: "На согласовании",
    ExpenseStatus.CLARIFICATION: "Уточнение",
    ExpenseStatus.APPROVED: "Одобрено",
    ExpenseStatus.REJECTED: "Отклонено",
    ExpenseStatus.NEEDS_REVISION: "Требует доработки",
    ExpenseStatus.TO_PAY: "К выплате",
    ExpenseStatus.REIMBURSED: "Компенсировано",
}


class NotifierPort(Protocol):
    """Outbound notifications decoupled from the Telegram SDK."""

    async def notify_manager_expense_card(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
        image_bytes: bytes | None,
    ) -> int:
        """Send (or re-send) the manager card with decision buttons; return message id."""
        ...

    async def clear_manager_decision_keyboard(self, *, manager: User, message_id: int) -> None:
        """Remove approve/reject/question buttons from the manager card."""
        ...

    async def notify_employee_decision(
        self,
        *,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        """Tell the employee the manager's decision (and optional reason/question)."""
        ...


def format_employee_decision(*, expense: Expense, detail: str | None = None) -> str:
    """Build the Telegram text for an employee status/decision notification."""
    task_id = expense.planfix_task_id if expense.planfix_task_id is not None else expense.id
    if expense.status is ExpenseStatus.APPROVED:
        return NOTIFY_EMPLOYEE_APPROVED.format(task_id=task_id)
    if expense.status is ExpenseStatus.REJECTED:
        return NOTIFY_EMPLOYEE_REJECTED.format(task_id=task_id, detail=detail or "—")
    if expense.status is ExpenseStatus.CLARIFICATION:
        return NOTIFY_EMPLOYEE_CLARIFICATION.format(task_id=task_id, detail=detail or "—")
    label = _STATUS_LABELS[expense.status]
    return f"Статус заявки №{task_id}: {label}"


__all__ = [
    "NOTIFY_EMPLOYEE_APPROVED",
    "NOTIFY_EMPLOYEE_CLARIFICATION",
    "NOTIFY_EMPLOYEE_REJECTED",
    "NotifierPort",
    "format_employee_decision",
]
