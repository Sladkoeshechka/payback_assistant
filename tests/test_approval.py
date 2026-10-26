from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.approval import (
    ApprovalForbiddenError,
    ApprovalService,
    ExpenseNotPendingError,
)
from payback.services.fakes import FakeNotifier, FakePlanfix


async def _people(session: AsyncSession) -> tuple[User, User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    other_manager = await users.create(
        telegram_id=1002,
        first_name="Other",
        last_name="Boss",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=1001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, other_manager, employee


async def _pending_expense(session: AsyncSession, employee_id: int) -> Expense:
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
    await expenses.set_status(expense, ExpenseStatus.PENDING)
    await expenses.set_manager_message(expense, 9001)
    await session.commit()
    return expense


def _service(
    session: AsyncSession, planfix: FakePlanfix, notifier: FakeNotifier
) -> ApprovalService:
    return ApprovalService(
        ExpensesRepo(session),
        planfix,
        notifier,
        Settings().planfix.statuses,
    )


async def test_approve_updates_planfix_local_status_and_notifies(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    result = await _service(session, planfix, notifier).approve(
        expense_id=expense.id, manager=manager
    )
    await session.commit()

    assert result.status is ExpenseStatus.APPROVED
    assert planfix.update_calls == 1
    assert planfix.task_updates[0] == (
        55,
        {"status": {"id": settings.planfix.statuses.approved}},
    )
    assert planfix.comment_calls == 0
    assert notifier.cleared_keyboards == [(manager.id, 9001)]
    assert len(notifier.employee_messages) == 1
    assert notifier.employee_messages[0]["status"] is ExpenseStatus.APPROVED


async def test_approve_keeps_local_status_when_notify_fails(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier(fail_on_employee_decision=True)
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    result = await _service(session, planfix, notifier).approve(
        expense_id=expense.id, manager=manager
    )

    assert result.status is ExpenseStatus.APPROVED
    reloaded = await ExpensesRepo(session).get_by_id(expense.id)
    assert reloaded is not None
    assert reloaded.status is ExpenseStatus.APPROVED
    assert planfix.update_calls == 1
    assert notifier.employee_messages == []


async def test_reject_writes_comment_and_reason(env: dict[str, str], session: AsyncSession) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    result = await _service(session, planfix, notifier).reject(
        expense_id=expense.id, manager=manager, reason="личная покупка"
    )
    await session.commit()

    assert result.status is ExpenseStatus.REJECTED
    assert planfix.task_updates[0][1] == {"status": {"id": settings.planfix.statuses.rejected}}
    assert planfix.comments == [(55, "Grace Hopper:\nПричина отказа: личная покупка", "user:7")]
    assert notifier.employee_messages[0]["detail"] == "личная покупка"


async def test_ask_moves_to_clarification(env: dict[str, str], session: AsyncSession) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    result = await _service(session, planfix, notifier).ask(
        expense_id=expense.id, manager=manager, question="Есть чек?"
    )
    await session.commit()

    assert result.status is ExpenseStatus.CLARIFICATION
    assert planfix.task_updates[0][1] == {"status": {"id": settings.planfix.statuses.clarification}}
    assert planfix.comments == [(55, "Grace Hopper:\nЕсть чек?", "user:7")]
    assert notifier.employee_messages[0]["detail"] == "Есть чек?"


async def test_double_approve_rejected_when_not_pending(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    service = _service(session, planfix, notifier)
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    await service.approve(expense_id=expense.id, manager=manager)
    await session.commit()

    with pytest.raises(ExpenseNotPendingError):
        await service.approve(expense_id=expense.id, manager=manager)
    assert planfix.update_calls == 1
    assert len(notifier.employee_messages) == 1


async def test_wrong_manager_is_forbidden(env: dict[str, str], session: AsyncSession) -> None:
    _, other_manager, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)

    with pytest.raises(ApprovalForbiddenError):
        await _service(session, planfix, notifier).approve(
            expense_id=expense.id, manager=other_manager
        )
    assert planfix.update_calls == 0
    assert notifier.employee_messages == []


async def test_approve_aborts_when_planfix_is_already_not_pending(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()
    planfix.seed_task(55, status_id=settings.planfix.statuses.to_pay)

    with pytest.raises(ExpenseNotPendingError):
        await _service(session, planfix, notifier).approve(expense_id=expense.id, manager=manager)

    reloaded = await ExpensesRepo(session).get_by_id(expense.id)
    assert reloaded is not None
    assert reloaded.status is ExpenseStatus.TO_PAY
    assert planfix.update_calls == 0
    assert notifier.employee_messages == []
