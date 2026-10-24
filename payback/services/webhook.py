"""Apply PlanFix task status changes from webhooks (stage 9C)."""

# ruff: noqa: RUF001

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from payback.config import PlanfixStatusIds
from payback.db.models import Expense, ExpenseStatus
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.ports import NotifierPort, PlanfixPort

logger = logging.getLogger(__name__)

# Russian status titles from the expense object (spec §5) — diagnostics only.
_STATUS_NAME_HINTS: dict[str, ExpenseStatus] = {
    "На согласовании": ExpenseStatus.PENDING,
    "Уточнение": ExpenseStatus.CLARIFICATION,
    "Одобрено": ExpenseStatus.APPROVED,
    "Отклонено": ExpenseStatus.REJECTED,
    "Требует доработки": ExpenseStatus.NEEDS_REVISION,
    "К выплате": ExpenseStatus.TO_PAY,
    "Компенсировано": ExpenseStatus.REIMBURSED,
}

_STATUSES_NEEDING_COMMENT = frozenset(
    {
        ExpenseStatus.REJECTED,
        ExpenseStatus.CLARIFICATION,
        ExpenseStatus.NEEDS_REVISION,
    }
)
_MAX_COMMENT_PAGES = 20


class WebhookService:
    """Reconcile local expenses with PlanFix after a verified webhook."""

    def __init__(
        self,
        expenses: ExpensesRepo,
        users: UsersRepo,
        planfix: PlanfixPort,
        notifier: NotifierPort,
        status_ids: PlanfixStatusIds,
    ) -> None:
        self._expenses = expenses
        self._users = users
        self._planfix = planfix
        self._notifier = notifier
        self._status_ids = status_ids

    async def apply(
        self, task_id: int, *, webhook_status_name: str | None = None
    ) -> Expense | None:
        """Re-fetch the task and update the local expense if the status changed."""
        task = await self._planfix.get_task(task_id)
        status_id = _status_id_from_task(task)
        if status_id is None:
            logger.warning(
                "planfix webhook task has no status id",
                extra={"planfix_task_id": task_id},
            )
            return None

        new_status = status_for_planfix_id(self._status_ids, status_id)
        if new_status is None:
            name_hint = (
                status_hint_from_name(webhook_status_name)
                if webhook_status_name is not None
                else None
            )
            logger.warning(
                "unknown planfix status id on webhook",
                extra={
                    "planfix_task_id": task_id,
                    "planfix_status_id": status_id,
                    "webhook_status_name": webhook_status_name,
                    "webhook_status_hint": name_hint.value if name_hint is not None else None,
                },
            )
            return None

        if webhook_status_name:
            _log_status_name_mismatch(webhook_status_name, new_status, task_id)

        expense = await self._expenses.get_by_planfix_task_id(task_id)
        if expense is None:
            logger.info(
                "planfix webhook for unknown local expense",
                extra={"planfix_task_id": task_id},
            )
            return None

        if expense.status is new_status:
            logger.info(
                "planfix webhook ignored (local status already matches)",
                extra={
                    "planfix_task_id": task_id,
                    "expense_id": expense.id,
                    "status": new_status.value,
                },
            )
            return expense

        detail = await self._latest_comment_detail(task_id, new_status)
        await self._expenses.set_status(expense, new_status)
        # Commit before Telegram side effects: HTTP 200 already went out, and a
        # notify failure must not leave local status behind PlanFix.
        await self._expenses.commit()
        await self._mark_manager_card(expense)
        await self._notify_employee(expense, detail=detail)
        return expense

    async def _latest_comment_detail(self, task_id: int, status: ExpenseStatus) -> str | None:
        if status not in _STATUSES_NEEDING_COMMENT:
            return None
        # Planfix has no dedicated "latest human comment" endpoint. We request one
        # comment per page and stop as soon as one human comment appears.
        for offset in range(_MAX_COMMENT_PAGES):
            comments = await self._planfix.list_comments(task_id, offset=offset, page_size=1)
            if comments:
                return comments[0].description
        return None

    async def _mark_manager_card(self, expense: Expense) -> None:
        if expense.manager_message_id is None:
            return
        employee = expense.employee
        if employee is None or employee.manager_id is None:
            return
        manager = await self._users.get_by_id(employee.manager_id)
        if manager is None:
            return
        try:
            await self._notifier.mark_manager_decision_in_planfix(
                manager=manager,
                employee=employee,
                expense=expense,
            )
        except Exception:
            logger.exception(
                "failed to mark manager card after planfix webhook",
                extra={"expense_id": expense.id, "planfix_task_id": expense.planfix_task_id},
            )

    async def _notify_employee(self, expense: Expense, *, detail: str | None) -> None:
        # Spec §4.5: TO_PAY is internal — do not notify the employee.
        if expense.status is ExpenseStatus.TO_PAY:
            return
        employee = expense.employee
        if employee is None:
            return
        try:
            await self._notifier.notify_employee_decision(
                employee=employee,
                expense=expense,
                detail=detail,
            )
        except Exception:
            logger.exception(
                "failed to notify employee after planfix webhook",
                extra={"expense_id": expense.id, "planfix_task_id": expense.planfix_task_id},
            )


def status_for_planfix_id(status_ids: PlanfixStatusIds, status_id: int) -> ExpenseStatus | None:
    """Map a configured PlanFix status id to the local enum."""
    mapping = {
        status_ids.pending: ExpenseStatus.PENDING,
        status_ids.clarification: ExpenseStatus.CLARIFICATION,
        status_ids.approved: ExpenseStatus.APPROVED,
        status_ids.rejected: ExpenseStatus.REJECTED,
        status_ids.needs_revision: ExpenseStatus.NEEDS_REVISION,
        status_ids.to_pay: ExpenseStatus.TO_PAY,
        status_ids.reimbursed: ExpenseStatus.REIMBURSED,
    }
    return mapping.get(status_id)


def status_hint_from_name(status_name: str | None) -> ExpenseStatus | None:
    """Best-effort status hint derived from webhook body text."""
    if status_name is None:
        return None
    return _STATUS_NAME_HINTS.get(status_name.strip())


def _status_id_from_task(task: Mapping[str, Any] | dict[str, Any]) -> int | None:
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    raw = status.get("id")
    return raw if isinstance(raw, int) else None


def _log_status_name_mismatch(
    webhook_status_name: str, resolved: ExpenseStatus, task_id: int
) -> None:
    hinted = status_hint_from_name(webhook_status_name)
    if hinted is not None and hinted is not resolved:
        logger.info(
            "planfix webhook status name differs from id mapping",
            extra={
                "planfix_task_id": task_id,
                "webhook_status_name": webhook_status_name,
                "resolved_status": resolved.value,
                "name_hint_status": hinted.value,
            },
        )


__all__ = ["WebhookService", "status_for_planfix_id", "status_hint_from_name"]
