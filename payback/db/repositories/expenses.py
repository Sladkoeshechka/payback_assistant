from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from payback.db.models import Expense, ExpenseStatus, User


class ExpensesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending_submission(
        self,
        *,
        employee_id: int,
        amount: Decimal,
        purchase_date: date,
        category_id: int,
        category_name: str,
        no_receipt: bool,
        direction_id: int | None = None,
        direction_name: str | None = None,
        comment: str | None = None,
        fn: str | None = None,
        fd: str | None = None,
        fp: str | None = None,
        telegram_file_id: str | None = None,
    ) -> Expense:
        expense = Expense(
            employee_id=employee_id,
            amount=amount,
            purchase_date=purchase_date,
            category_id=category_id,
            category_name=category_name,
            direction_id=direction_id,
            direction_name=direction_name,
            comment=comment,
            fn=fn,
            fd=fd,
            fp=fp,
            no_receipt=no_receipt,
            telegram_file_id=telegram_file_id,
        )
        self._session.add(expense)
        await self._session.flush()
        return expense

    async def get_by_id(self, expense_id: int) -> Expense | None:
        return await self._session.scalar(
            select(Expense)
            .where(Expense.id == expense_id)
            .options(selectinload(Expense.employee))
        )

    async def get_by_planfix_task_id(self, planfix_task_id: int) -> Expense | None:
        return await self._session.scalar(
            select(Expense).where(Expense.planfix_task_id == planfix_task_id)
        )

    async def get_by_fiscal_data(self, fn: str, fd: str, fp: str) -> Expense | None:
        return await self._session.scalar(
            select(Expense).where(Expense.fn == fn, Expense.fd == fd, Expense.fp == fp)
        )

    async def set_planfix_task(self, expense: Expense, planfix_task_id: int) -> None:
        expense.planfix_task_id = planfix_task_id
        await self._session.flush()

    async def set_planfix_file(self, expense: Expense, planfix_file_id: int) -> None:
        expense.planfix_file_id = planfix_file_id
        await self._session.flush()

    async def set_manager_message(self, expense: Expense, message_id: int) -> None:
        expense.manager_message_id = message_id
        await self._session.flush()

    async def set_status(self, expense: Expense, status: ExpenseStatus) -> None:
        expense.status = status
        await self._session.flush()

    async def list_for_employee_since(self, employee_id: int, since: datetime) -> list[Expense]:
        """Return an employee's expenses created at or after ``since``, newest first."""
        result = await self._session.scalars(
            select(Expense)
            .where(Expense.employee_id == employee_id, Expense.created_at >= since)
            .order_by(Expense.created_at.desc(), Expense.id.desc())
        )
        return list(result)

    async def list_pending_for_manager(self, manager_id: int) -> list[Expense]:
        """Return subordinates' expenses waiting for this manager's decision."""
        result = await self._session.scalars(
            select(Expense)
            .join(User, Expense.employee_id == User.id)
            .where(
                User.manager_id == manager_id,
                Expense.status == ExpenseStatus.PENDING,
            )
            .options(selectinload(Expense.employee))
            .order_by(Expense.created_at.asc(), Expense.id.asc())
        )
        return list(result)
