"""Manager decisions on pending expenses (stage 8A)."""


from payback.config import PlanfixStatusIds
from payback.db.models import Expense, ExpenseStatus, User
from payback.db.repositories.expenses import ExpensesRepo
from payback.services.ports import NotifierPort, PlanfixPort


class ApprovalError(Exception):
    """Base class for approval-flow failures."""


class ExpenseNotFoundError(ApprovalError):
    """No expense exists for the requested id."""


class ApprovalForbiddenError(ApprovalError):
    """The manager may not decide on this expense."""


class ExpenseNotPendingError(ApprovalError):
    """The expense is not waiting for a manager decision (already decided)."""


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
        await self._finish_ui(manager=manager, employee=employee, expense=expense)
        return expense

    async def reject(self, *, expense_id: int, manager: User, reason: str) -> Expense:
        expense, employee = await self._load_pending_for_manager(expense_id, manager)
        await self._push_planfix(
            expense,
            status_id=self._status_ids.rejected,
            comment=f"Причина отказа: {reason}",
        )
        await self._expenses.set_status(expense, ExpenseStatus.REJECTED)
        await self._finish_ui(
            manager=manager, employee=employee, expense=expense, detail=reason
        )
        return expense

    async def ask(self, *, expense_id: int, manager: User, question: str) -> Expense:
        expense, employee = await self._load_pending_for_manager(expense_id, manager)
        await self._push_planfix(
            expense,
            status_id=self._status_ids.clarification,
            comment=question,
        )
        await self._expenses.set_status(expense, ExpenseStatus.CLARIFICATION)
        await self._finish_ui(
            manager=manager, employee=employee, expense=expense, detail=question
        )
        return expense

    async def _load_pending_for_manager(
        self, expense_id: int, manager: User
    ) -> tuple[Expense, User]:
        expense = await self._expenses.get_by_id(expense_id)
        if expense is None:
            raise ExpenseNotFoundError(f"expense {expense_id} not found")
        employee = expense.employee
        if employee is None or employee.manager_id != manager.id:
            raise ApprovalForbiddenError("manager cannot decide on this expense")
        if expense.status is not ExpenseStatus.PENDING:
            raise ExpenseNotPendingError(f"expense {expense_id} is {expense.status}")
        return expense, employee

    async def _push_planfix(
        self,
        expense: Expense,
        *,
        status_id: int,
        comment: str | None = None,
    ) -> None:
        if expense.planfix_task_id is None:
            return
        await self._planfix.update_task(
            expense.planfix_task_id, {"status": {"id": status_id}}
        )
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


__all__ = [
    "ApprovalError",
    "ApprovalForbiddenError",
    "ApprovalService",
    "ExpenseNotFoundError",
    "ExpenseNotPendingError",
]
