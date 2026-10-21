"""Employee replies while an expense needs revision (stage 8D)."""


from payback.config import PlanfixStatusIds
from payback.db.models import Expense, ExpenseStatus, User
from payback.db.repositories.expenses import ExpensesRepo
from payback.services.ports import PlanfixPort


class RevisionError(Exception):
    """Base class for needs-revision reply failures."""


class NoRevisionPendingError(RevisionError):
    """The employee has no expense waiting for a revision reply."""


class RevisionService:
    """Apply an employee's text/photo answer and return the expense to approved."""

    def __init__(
        self,
        expenses: ExpensesRepo,
        planfix: PlanfixPort,
        status_ids: PlanfixStatusIds,
    ) -> None:
        self._expenses = expenses
        self._planfix = planfix
        self._status_ids = status_ids

    async def reply(
        self,
        *,
        employee: User,
        text: str | None = None,
        image_bytes: bytes | None = None,
        image_filename: str = "reply.jpg",
        image_content_type: str = "image/jpeg",
    ) -> Expense:
        if text is None and image_bytes is None:
            raise ValueError("revision reply needs text or an image")
        expense = await self._expenses.get_needs_revision_for_employee(employee.id)
        if expense is None:
            raise NoRevisionPendingError(f"employee {employee.id} has no needs-revision expense")

        await self._push_planfix(
            expense,
            text=text,
            image_bytes=image_bytes,
            image_filename=image_filename,
            image_content_type=image_content_type,
        )
        await self._expenses.set_status(expense, ExpenseStatus.APPROVED)
        return expense

    async def _push_planfix(
        self,
        expense: Expense,
        *,
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
        comment = text if text is not None else "Ответ сотрудника (фото)"
        await self._planfix.add_comment(task_id, comment)
        await self._planfix.update_task(
            task_id, {"status": {"id": self._status_ids.approved}}
        )


__all__ = [
    "NoRevisionPendingError",
    "RevisionError",
    "RevisionService",
]
