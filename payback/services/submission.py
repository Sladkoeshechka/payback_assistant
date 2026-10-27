"""Push a confirmed expense draft into the local DB and PlanFix."""

# ruff: noqa: RUF001

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.config import PlanfixFieldIds
from payback.db.models import Expense, ExpenseStatus, User
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.planfix.exceptions import PlanfixError
from payback.services.draft import SubmissionDraft
from payback.services.expense_card import (
    custom_field_data_for_expense,
    employee_display_name,
    task_name,
)
from payback.services.notifications import NOTIFY_EMPLOYEE_SUBMITTED
from payback.services.ports import NotifierPort, PlanfixPort

logger = logging.getLogger(__name__)

PENDING_FLUSH_INTERVAL_SECONDS = 60.0

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


class DuplicateReceiptError(ValueError):
    """A fiscal QR triple was already used by another expense."""

    def __init__(self, existing: Expense) -> None:
        self.existing = existing
        super().__init__(format_duplicate_receipt_message(existing))


def format_duplicate_receipt_message(existing: Expense) -> str:
    """Build the user-visible duplicate-receipt line."""
    submitted = existing.created_at.strftime("%d.%m.%Y")
    if existing.planfix_task_id is not None:
        reference = f"№{existing.planfix_task_id}"
    else:
        reference = f"#{existing.id}"
    status = _STATUS_LABELS[existing.status]
    return f"Этот чек уже подан {submitted} (заявка {reference}, статус: {status})."


class SubmissionService:
    """Create or resume Planfix publication for one expense."""

    def __init__(
        self,
        expenses: ExpensesRepo,
        planfix: PlanfixPort,
        notifier: NotifierPort,
        field_ids: PlanfixFieldIds,
    ) -> None:
        self._expenses = expenses
        self._planfix = planfix
        self._notifier = notifier
        self._field_ids = field_ids

    async def submit(
        self,
        draft: SubmissionDraft,
        *,
        employee: User,
        manager: User | None,
    ) -> Expense:
        """Persist a new expense from a draft and publish it to Planfix."""
        await self._reject_duplicate(draft)
        if (
            draft.amount is None
            or draft.purchase_date is None
            or draft.category_id is None
            or draft.category_name is None
        ):
            raise ValueError("submission draft is incomplete")
        expense = await self._expenses.create_pending_submission(
            employee_id=employee.id,
            amount=draft.amount,
            purchase_date=draft.purchase_date,
            category_id=draft.category_id,
            category_name=draft.category_name,
            no_receipt=draft.no_receipt,
            direction_id=draft.direction_id,
            direction_name=draft.direction_name,
            comment=draft.comment,
            fn=draft.fn,
            fd=draft.fd,
            fp=draft.fp,
            telegram_file_id=draft.telegram_file_id,
        )
        return await self._publish_quietly(
            expense,
            employee=employee,
            manager=manager,
            image_bytes=draft.image_bytes,
            image_filename=draft.image_filename,
            image_content_type=draft.image_content_type,
        )

    async def resume(
        self,
        expense: Expense,
        *,
        employee: User,
        manager: User | None,
        image_bytes: bytes | None = None,
        image_filename: str = "receipt.jpg",
        image_content_type: str = "image/jpeg",
    ) -> Expense:
        """Finish Planfix steps left incomplete after a previous failure."""
        if expense.status is ExpenseStatus.PENDING:
            await self._notify_manager_if_needed(
                expense,
                employee=employee,
                manager=manager,
                image_bytes=image_bytes,
            )
            return expense
        if expense.status is not ExpenseStatus.PENDING_SUBMISSION:
            return expense
        return await self._publish_quietly(
            expense,
            employee=employee,
            manager=manager,
            image_bytes=image_bytes,
            image_filename=image_filename,
            image_content_type=image_content_type,
        )

    async def _publish_quietly(
        self,
        expense: Expense,
        *,
        employee: User,
        manager: User | None,
        image_bytes: bytes | None,
        image_filename: str,
        image_content_type: str,
    ) -> Expense:
        """Publish to Planfix; on API failure keep the local row for later resume."""
        try:
            return await self._publish(
                expense,
                employee=employee,
                manager=manager,
                image_bytes=image_bytes,
                image_filename=image_filename,
                image_content_type=image_content_type,
            )
        except PlanfixError:
            return expense

    async def _publish(
        self,
        expense: Expense,
        *,
        employee: User,
        manager: User | None,
        image_bytes: bytes | None,
        image_filename: str,
        image_content_type: str,
    ) -> Expense:
        if expense.planfix_task_id is None:
            employee_name = employee_display_name(
                first_name=employee.first_name, last_name=employee.last_name
            )
            task_id = await self._planfix.create_task(
                expense.id,
                name=task_name(
                    amount=expense.amount,
                    category_name=expense.category_name,
                    employee_name=employee_name,
                ),
                description=expense.comment,
                manager_planfix_user_id=(manager.planfix_user_id if manager is not None else None),
                custom_field_data=custom_field_data_for_expense(
                    expense,
                    employee_name=employee_name,
                    field_ids=self._field_ids,
                ),
            )
            await self._expenses.set_planfix_task(expense, task_id)

        assert expense.planfix_task_id is not None

        if image_bytes is not None and expense.planfix_file_id is None:
            file_id = await self._planfix.upload_file(
                image_bytes,
                filename=image_filename,
                content_type=image_content_type,
            )
            await self._expenses.set_planfix_file(expense, file_id)

        if (
            expense.planfix_file_id is not None
            and expense.status is ExpenseStatus.PENDING_SUBMISSION
        ):
            # Re-attach is safe on resume when upload finished but attach/status did not.
            await self._planfix.attach_file(expense.planfix_file_id, expense.planfix_task_id)

        await self._expenses.set_status(expense, ExpenseStatus.PENDING)
        await self._notify_manager_if_needed(
            expense,
            employee=employee,
            manager=manager,
            image_bytes=image_bytes,
        )
        return expense

    async def _notify_manager_if_needed(
        self,
        expense: Expense,
        *,
        employee: User,
        manager: User | None,
        image_bytes: bytes | None,
    ) -> None:
        if manager is None or expense.manager_message_id is not None:
            return
        message_id = await self._notifier.notify_manager_expense_card(
            manager=manager,
            employee=employee,
            expense=expense,
            image_bytes=image_bytes,
        )
        await self._expenses.set_manager_message(expense, message_id)

    async def _reject_duplicate(self, draft: SubmissionDraft) -> None:
        if not draft.has_fiscal_ids:
            return
        assert draft.fn is not None and draft.fd is not None and draft.fp is not None
        existing = await self._expenses.get_by_fiscal_data(draft.fn, draft.fd, draft.fp)
        if existing is not None:
            raise DuplicateReceiptError(existing)


DownloadFile = Callable[[str], Awaitable[bytes]]


async def flush_pending_submissions(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    planfix: PlanfixPort,
    notifier: NotifierPort,
    field_ids: PlanfixFieldIds,
    download_file: DownloadFile | None = None,
) -> int:
    """Claim and resume ``pending_submission`` rows one-by-one; notify on success.

    Each claim uses a row lock (``SKIP LOCKED`` on Postgres) so concurrent flushers
    do not publish the same expense twice. Rows still pending after an attempt are
    not retried again in the same pass.
    """
    done = 0
    attempted: set[int] = set()
    while True:
        async with session_factory() as session:
            expenses = ExpensesRepo(session)
            users = UsersRepo(session)
            expense = await expenses.claim_next_pending_submission()
            if expense is None:
                break
            if expense.id in attempted:
                await session.rollback()
                break
            attempted.add(expense.id)
            service = SubmissionService(expenses, planfix, notifier, field_ids)
            try:
                image_bytes = None
                if expense.telegram_file_id and download_file is not None:
                    image_bytes = await download_file(expense.telegram_file_id)
                manager = (
                    await users.get_by_id(expense.employee.manager_id)
                    if expense.employee.manager_id is not None
                    else None
                )
                updated = await service.resume(
                    expense,
                    employee=expense.employee,
                    manager=manager,
                    image_bytes=image_bytes,
                )
                await expenses.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "pending submission flush failed",
                    extra={"expense_id": expense.id},
                )
                continue
            if updated.status is ExpenseStatus.PENDING and updated.planfix_task_id is not None:
                await notifier.notify_employee_text(
                    employee=expense.employee,
                    text=NOTIFY_EMPLOYEE_SUBMITTED.format(task_id=updated.planfix_task_id),
                )
                done += 1
    return done


async def pending_flush_loop(
    stop: asyncio.Event,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    planfix: PlanfixPort,
    notifier: NotifierPort,
    field_ids: PlanfixFieldIds,
    download_file: DownloadFile | None = None,
    interval: float = PENDING_FLUSH_INTERVAL_SECONDS,
) -> None:
    """Until ``stop``, periodically call :func:`flush_pending_submissions`."""
    while not stop.is_set():
        try:
            await flush_pending_submissions(
                session_factory,
                planfix=planfix,
                notifier=notifier,
                field_ids=field_ids,
                download_file=download_file,
            )
        except Exception:
            logger.exception("pending submission flush loop failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


__all__ = [
    "PENDING_FLUSH_INTERVAL_SECONDS",
    "DuplicateReceiptError",
    "SubmissionService",
    "flush_pending_submissions",
    "format_duplicate_receipt_message",
    "pending_flush_loop",
]
