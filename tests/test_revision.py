from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.fakes import FakePlanfix
from payback.services.revision import NoRevisionPendingError, RevisionService


async def _people(session: AsyncSession) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=3000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=3001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, employee


async def _needs_revision_expense(session: AsyncSession, employee_id: int) -> Expense:
    expenses = ExpensesRepo(session)
    expense = await expenses.create_pending_submission(
        employee_id=employee_id,
        amount=Decimal("100.00"),
        purchase_date=date(2026, 10, 1),
        category_id=7,
        category_name="Материалы",
        no_receipt=True,
        comment="taxi",
    )
    await expenses.set_planfix_task(expense, 55)
    await expenses.set_status(expense, ExpenseStatus.NEEDS_REVISION)
    await session.commit()
    return expense


def _service(session: AsyncSession, planfix: FakePlanfix) -> RevisionService:
    return RevisionService(
        ExpensesRepo(session),
        planfix,
        Settings().planfix.statuses,
    )


async def test_reply_text_moves_to_approved(env: dict[str, str], session: AsyncSession) -> None:
    _, employee = await _people(session)
    await _needs_revision_expense(session, employee.id)
    planfix = FakePlanfix()
    settings = Settings()

    result = await _service(session, planfix).reply(employee=employee, text="Приложил счет")
    await session.commit()

    assert result.status is ExpenseStatus.APPROVED
    assert planfix.comments == [(55, "Ada Lovelace:\nПриложил счет", "user:7")]
    assert planfix.task_updates == [(55, {"status": {"id": settings.planfix.statuses.approved}})]
    assert planfix.upload_calls == 0


async def test_reply_photo_uploads_and_attaches(env: dict[str, str], session: AsyncSession) -> None:
    _, employee = await _people(session)
    await _needs_revision_expense(session, employee.id)
    planfix = FakePlanfix()

    result = await _service(session, planfix).reply(
        employee=employee,
        text="Скан",
        image_bytes=b"fake-image",
    )
    await session.commit()

    assert result.status is ExpenseStatus.APPROVED
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert planfix.comments == [(55, "Ada Lovelace:\nСкан", "user:7")]


async def test_reply_when_not_needs_revision_raises(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    planfix = FakePlanfix()

    with pytest.raises(NoRevisionPendingError):
        await _service(session, planfix).reply(employee=employee, text="поздно")
    assert planfix.comment_calls == 0


async def test_second_reply_rejected_when_already_approved(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    await _needs_revision_expense(session, employee.id)
    planfix = FakePlanfix()
    service = _service(session, planfix)

    await service.reply(employee=employee, text="первый")
    await session.commit()

    with pytest.raises(NoRevisionPendingError):
        await service.reply(employee=employee, text="второй")
    assert planfix.comment_calls == 1
