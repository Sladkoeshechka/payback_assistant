from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from payback.db.models import ExpenseStatus, UserRole
from payback.db.repositories import ExpensesRepo, InvitesRepo, UsersRepo


async def create_employee(users: UsersRepo) -> int:
    employee = await users.create(
        telegram_id=1001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
    )
    return employee.id


async def test_users_support_manager_relationships_and_owner_bootstrap(
    session: AsyncSession,
) -> None:
    users = UsersRepo(session)

    manager, created = await users.get_or_create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    same_manager, created_again = await users.get_or_create(
        telegram_id=1000,
        first_name="Changed",
        last_name="Name",
        role=UserRole.EMPLOYEE,
    )
    employee = await users.create(
        telegram_id=1001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )

    assert created is True
    assert created_again is False
    assert same_manager.id == manager.id
    assert (await users.get_by_telegram_id(1000)) is manager
    assert await users.list_active_subordinates(manager.id) == [employee]

    await users.link_planfix_user(manager, 9001)
    await users.set_active(employee, False)

    assert manager.planfix_user_id == 9001
    assert await users.list_active_subordinates(manager.id) == []


async def test_invites_only_return_unexpired_unconsumed_unrevoked_codes(
    session: AsyncSession,
) -> None:
    users = UsersRepo(session)
    invites = InvitesRepo(session)
    manager, _ = await users.get_or_create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    employee_id = await create_employee(users)
    now = datetime.now(UTC)

    active = await invites.create(
        code="active-code",
        role=UserRole.EMPLOYEE,
        created_by_id=manager.id,
        expires_at=now + timedelta(days=1),
    )
    expired = await invites.create(
        code="expired-code",
        role=UserRole.EMPLOYEE,
        created_by_id=manager.id,
        expires_at=now - timedelta(seconds=1),
    )
    revoked = await invites.create(
        code="revoked-code",
        role=UserRole.EMPLOYEE,
        created_by_id=manager.id,
        expires_at=now + timedelta(days=1),
    )
    await invites.revoke(revoked, now)

    assert await invites.get_active_by_code(active.code, now) is active
    assert await invites.get_active_by_code(expired.code, now) is None
    assert await invites.get_active_by_code(revoked.code, now) is None
    assert await invites.list_active_for_creator(manager.id, now) == [active]

    await invites.consume(active, employee_id, now)

    assert await invites.get_active_by_code(active.code, now) is None
    assert active.used_by_id == employee_id
    assert active.used_at == now


async def test_expenses_persist_submission_and_planfix_progress(session: AsyncSession) -> None:
    users = UsersRepo(session)
    expenses = ExpensesRepo(session)
    employee_id = await create_employee(users)

    expense = await expenses.create_pending_submission(
        employee_id=employee_id,
        amount=Decimal("123.45"),
        purchase_date=date(2026, 9, 30),
        category_id=7,
        category_name="Materials",
        direction_id=3,
        direction_name="Office",
        comment="Printer paper",
        fn="9282440300671549",
        fd="12345",
        fp="67890",
        no_receipt=False,
        telegram_file_id="telegram-photo-id",
    )

    assert expense.status is ExpenseStatus.PENDING_SUBMISSION
    assert expense.created_at.tzinfo is UTC
    assert expense.updated_at.tzinfo is UTC
    assert await expenses.get_by_fiscal_data("9282440300671549", "12345", "67890") is expense

    await expenses.set_planfix_task(expense, 8001)
    await expenses.set_planfix_file(expense, 7001)
    await expenses.set_manager_message(expense, 6001)
    await expenses.set_status(expense, ExpenseStatus.PENDING)

    assert await expenses.get_by_id(expense.id) is expense
    assert await expenses.get_by_planfix_task_id(8001) is expense
    assert expense.planfix_file_id == 7001
    assert expense.manager_message_id == 6001
    assert expense.status.value == "pending"
    assert (
        await session.scalar(
            text("SELECT status FROM expenses WHERE id = :expense_id").bindparams(
                expense_id=expense.id
            )
        )
    ) == "pending"


async def test_fiscal_data_must_be_unique(session: AsyncSession) -> None:
    users = UsersRepo(session)
    expenses = ExpensesRepo(session)
    employee_id = await create_employee(users)
    await expenses.create_pending_submission(
        employee_id=employee_id,
        amount=Decimal("1.00"),
        purchase_date=date(2026, 9, 30),
        category_id=7,
        category_name="Materials",
        fn="fn",
        fd="fd",
        fp="fp",
        no_receipt=False,
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await expenses.create_pending_submission(
            employee_id=employee_id,
            amount=Decimal("2.00"),
            purchase_date=date(2026, 9, 30),
            category_id=7,
            category_name="Materials",
            fn="fn",
            fd="fd",
            fp="fp",
            no_receipt=False,
        )

    await session.rollback()


async def test_expenses_without_fiscal_data_do_not_conflict(session: AsyncSession) -> None:
    users = UsersRepo(session)
    expenses = ExpensesRepo(session)
    employee_id = await create_employee(users)

    first = await expenses.create_pending_submission(
        employee_id=employee_id,
        amount=Decimal("1.00"),
        purchase_date=date(2026, 9, 30),
        category_id=7,
        category_name="Materials",
        no_receipt=True,
    )
    second = await expenses.create_pending_submission(
        employee_id=employee_id,
        amount=Decimal("2.00"),
        purchase_date=date(2026, 9, 30),
        category_id=7,
        category_name="Materials",
        no_receipt=True,
    )

    assert first.id != second.id
