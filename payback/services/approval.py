"""Manager decisions on pending expenses."""

import logging
from collections.abc import Mapping
from typing import Any

from payback.config import PlanfixStatusIds
from payback.db.models import Expense, ExpenseStatus, User
from payback.db.repositories.expenses import ExpensesRepo
from payback.services.planfix_text import attributed_comment
from payback.services.ports import NotifierPort, PlanfixPort

logger = logging.getLogger(__name__)


class ApprovalError(Exception):
    """Base class for approval-flow failures."""


class ExpenseNotFoundError(ApprovalError):
    """No expense exists for the requested id."""


class ApprovalForbiddenError(ApprovalError):
    """The manager may not decide on this expense."""


class ExpenseNotPendingError(ApprovalError):
    """The expense is not waiting for a manager decision (already decided)."""


_STATUS_BY_ID_ATTR = {
    "pending": ExpenseStatus.PENDING,
    "clarification": ExpenseStatus.CLARIFICATION,
    "approved": ExpenseStatus.APPROVED,
    "rejected": ExpenseStatus.REJECTED,
    "needs_revision": ExpenseStatus.NEEDS_REVISION,
    "to_pay": ExpenseStatus.TO_PAY,
    "reimbursed": ExpenseStatus.REIMBURSED,
}


class ApprovalService:
    """Apply approve / reject / clarification for a manager's subordinate."""

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

    async def approve(self, *, expense_id: int, manager: User) -> Expense:
        expense, employee = await self._load_pending_for_manager(expense_id, manager)
        await self._push_planfix(expense, status_id=self._status_ids.approved)
        await self._expenses.set_status(expense, ExpenseStatus.APPROVED)
        # Commit before Telegram side effects so a notify failure cannot undo PlanFix.
        await self._expenses.commit()
        await self._finish_ui(manager=manager, employee=employee, expense=expense)
        return expense

    async def reject(self, *, expense_id: int, manager: User, reason: str) -> Expense:
        expense, employee = await self._load_pending_for_manager(expense_id, manager)
        await self._push_planfix(
            expense,
            status_id=self._status_ids.rejected,
            comment=attributed_comment(manager, f"Причина отказа: {reason}"),
        )
        await self._expenses.set_status(expense, ExpenseStatus.REJECTED)
        await self._expenses.commit()
        await self._finish_ui(manager=manager, employee=employee, expense=expense, detail=reason)
        return expense

    async def ask(self, *, expense_id: int, manager: User, question: str) -> Expense:
        expense, employee = await self._load_pending_for_manager(expense_id, manager)
        await self._push_planfix(
            expense,
            status_id=self._status_ids.clarification,
            comment=attributed_comment(manager, question),
        )
        await self._expenses.set_status(expense, ExpenseStatus.CLARIFICATION)
        await self._expenses.commit()
        await self._finish_ui(manager=manager, employee=employee, expense=expense, detail=question)
        return expense

    async def _load_pending_for_manager(
        self, expense_id: int, manager: User
    ) -> tuple[Expense, User]:
        expense = await self._expenses.get_by_id_for_update(expense_id)
        if expense is None:
            raise ExpenseNotFoundError(f"expense {expense_id} not found")
        employee = expense.employee
        if employee is None or employee.manager_id != manager.id:
            raise ApprovalForbiddenError("manager cannot decide on this expense")
        if expense.status is not ExpenseStatus.PENDING:
            raise ExpenseNotPendingError(f"expense {expense_id} is {expense.status}")
        await self._ensure_planfix_still_pending(expense)
        return expense, employee

    async def _ensure_planfix_still_pending(self, expense: Expense) -> None:
        if expense.planfix_task_id is None:
            return
        task = await self._planfix.get_task(expense.planfix_task_id)
        status_id = _status_id_from_task(task)
        if status_id == self._status_ids.pending:
            return
        resolved = _status_for_planfix_id(self._status_ids, status_id)
        if resolved is not None and expense.status is not resolved:
            await self._expenses.set_status(expense, resolved)
        raise ExpenseNotPendingError(
            f"planfix task {expense.planfix_task_id} status is {status_id}, expected pending"
        )

    async def _push_planfix(
        self,
        expense: Expense,
        *,
        status_id: int,
        comment: str | None = None,
    ) -> None:
        if expense.planfix_task_id is None:
            return
        await self._planfix.update_task(expense.planfix_task_id, {"status": {"id": status_id}})
        if comment:
            await self._planfix.add_comment(expense.planfix_task_id, comment)

    async def _finish_ui(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        try:
            if expense.manager_message_id is not None:
                await self._notifier.clear_manager_decision_keyboard(
                    manager=manager,
                    message_id=expense.manager_message_id,
                )
            await self._notifier.notify_employee_decision(
                employee=employee,
                expense=expense,
                detail=detail,
            )
        except Exception:
            logger.exception(
                "failed to notify after manager decision",
                extra={"expense_id": expense.id, "status": expense.status.value},
            )


__all__ = [
    "ApprovalError",
    "ApprovalForbiddenError",
    "ApprovalService",
    "ExpenseNotFoundError",
    "ExpenseNotPendingError",
]


def _status_id_from_task(task: Mapping[str, Any] | dict[str, Any]) -> int | None:
    status = task.get("status")
    if not isinstance(status, dict):
        return None
    raw = status.get("id")
    return raw if isinstance(raw, int) else None


def _status_for_planfix_id(
    status_ids: PlanfixStatusIds, status_id: int | None
) -> ExpenseStatus | None:
    if status_id is None:
        return None
    for attr_name, status in _STATUS_BY_ID_ATTR.items():
        if getattr(status_ids, attr_name) == status_id:
            return status
    return None
