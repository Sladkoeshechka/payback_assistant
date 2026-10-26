"""Outbound notification contract and employee message bodies (no aiogram)."""

# ruff: noqa: RUF001

from html import escape
from typing import Protocol

from payback.db.models import Expense, ExpenseStatus, User

NOTIFY_EMPLOYEE_APPROVED = "Заявка №{task_id} одобрена."
NOTIFY_EMPLOYEE_REJECTED = "Заявка №{task_id} отклонена.\nПричина: {detail}"
NOTIFY_EMPLOYEE_REJECTED_NO_DETAIL = "Заявка №{task_id} отклонена."
NOTIFY_EMPLOYEE_CLARIFICATION = "По заявке №{task_id} нужен ответ.\nВопрос: {detail}"
NOTIFY_EMPLOYEE_CLARIFICATION_NO_DETAIL = "По заявке №{task_id} нужен ответ."
NOTIFY_EMPLOYEE_NEEDS_REVISION = (
    "По заявке №{task_id} нужна доработка.\n"
    "Комментарий бухгалтера: {detail}\n"
    "Ответьте текстом или фото в этот чат."
)
NOTIFY_EMPLOYEE_NEEDS_REVISION_NO_DETAIL = (
    "По заявке №{task_id} нужна доработка.\nОтветьте текстом или фото в этот чат."
)

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
        reply_text: str | None = None,
    ) -> int:
        """Send (or re-send) the manager card with decision buttons; return message id."""
        ...

    async def clear_manager_decision_keyboard(self, *, manager: User, message_id: int) -> None:
        """Remove approve/reject/question buttons from the manager card."""
        ...

    async def mark_manager_decision_in_planfix(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
    ) -> None:
        """Clear buttons and note that the decision was made in PlanFix."""
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
    # Bot default parse mode is HTML; PlanFix/manager text may contain <>& .
    safe_detail = escape(detail) if detail else None
    if expense.status is ExpenseStatus.APPROVED:
        return NOTIFY_EMPLOYEE_APPROVED.format(task_id=task_id)
    if expense.status is ExpenseStatus.REJECTED:
        if safe_detail is None:
            return NOTIFY_EMPLOYEE_REJECTED_NO_DETAIL.format(task_id=task_id)
        return NOTIFY_EMPLOYEE_REJECTED.format(task_id=task_id, detail=safe_detail)
    if expense.status is ExpenseStatus.CLARIFICATION:
        if safe_detail is None:
            return NOTIFY_EMPLOYEE_CLARIFICATION_NO_DETAIL.format(task_id=task_id)
        return NOTIFY_EMPLOYEE_CLARIFICATION.format(task_id=task_id, detail=safe_detail)
    if expense.status is ExpenseStatus.NEEDS_REVISION:
        if safe_detail is None:
            return NOTIFY_EMPLOYEE_NEEDS_REVISION_NO_DETAIL.format(task_id=task_id)
        return NOTIFY_EMPLOYEE_NEEDS_REVISION.format(task_id=task_id, detail=safe_detail)
    label = _STATUS_LABELS[expense.status]
    return f"Статус заявки №{task_id}: {label}"


__all__ = [
    "NOTIFY_EMPLOYEE_APPROVED",
    "NOTIFY_EMPLOYEE_CLARIFICATION",
    "NOTIFY_EMPLOYEE_CLARIFICATION_NO_DETAIL",
    "NOTIFY_EMPLOYEE_NEEDS_REVISION",
    "NOTIFY_EMPLOYEE_NEEDS_REVISION_NO_DETAIL",
    "NOTIFY_EMPLOYEE_REJECTED",
    "NOTIFY_EMPLOYEE_REJECTED_NO_DETAIL",
    "NotifierPort",
    "format_employee_decision",
]
