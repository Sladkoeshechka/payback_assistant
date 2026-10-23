# ruff: noqa: RUF001

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.fakes import FakeNotifier, FakePlanfix
from payback.services.webhook import (
    WebhookService,
    status_for_planfix_id,
    status_hint_from_name,
)


async def _people(session: AsyncSession) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
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
    return manager, employee


async def _pending_expense(session: AsyncSession, employee_id: int, task_id: int = 55) -> Expense:
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
    await expenses.set_planfix_task(expense, task_id)
    await expenses.set_status(expense, ExpenseStatus.PENDING)
    await expenses.set_manager_message(expense, 9001)
    await session.commit()
    return expense


def _service(session: AsyncSession, planfix: FakePlanfix, notifier: FakeNotifier) -> WebhookService:
    return WebhookService(
        ExpensesRepo(session),
        UsersRepo(session),
        planfix,
        notifier,
        Settings().planfix.statuses,
    )


async def test_status_for_planfix_id_maps_configured_ids(env: dict[str, str]) -> None:
    ids = Settings().planfix.statuses
    assert status_for_planfix_id(ids, ids.approved) is ExpenseStatus.APPROVED
    assert status_for_planfix_id(ids, 999_999) is None


async def test_status_hint_from_name_maps_known_values() -> None:
    assert status_hint_from_name("Одобрено") is ExpenseStatus.APPROVED
    assert status_hint_from_name("  К выплате  ") is ExpenseStatus.TO_PAY
    assert status_hint_from_name("Неизвестный статус") is None
    assert status_hint_from_name(None) is None


async def test_apply_approved_updates_notifies_and_marks_manager(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    settings = Settings()
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(55, webhook_status_name="Одобрено")
    await session.commit()

    assert result is not None
    assert result.status is ExpenseStatus.APPROVED
    assert planfix.get_task_calls == 1
    assert planfix.list_comments_calls == 0
    assert notifier.employee_messages == [
        {
            "employee_id": employee.id,
            "expense_id": expense.id,
            "status": ExpenseStatus.APPROVED,
            "detail": None,
        }
    ]
    assert notifier.planfix_decision_marks == [
        {
            "manager_id": manager.id,
            "employee_id": employee.id,
            "expense_id": expense.id,
            "message_id": 9001,
        }
    ]


async def test_apply_echo_when_local_already_matches(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    settings = Settings()
    expenses = ExpensesRepo(session)
    await expenses.set_status(expense, ExpenseStatus.APPROVED)
    await session.commit()

    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(55)
    await session.commit()

    assert result is not None
    assert result.status is ExpenseStatus.APPROVED
    assert notifier.employee_messages == []
    assert notifier.planfix_decision_marks == []


async def test_apply_rejected_reads_latest_comment(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    await _pending_expense(session, employee.id)
    settings = Settings()
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.rejected)
    planfix.comments.append((55, "старый комментарий"))
    planfix.comments.append((55, "личная покупка"))
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(55, webhook_status_name="Отклонено")
    await session.commit()

    assert result is not None
    assert result.status is ExpenseStatus.REJECTED
    assert planfix.list_comments_calls == 1
    assert planfix.comment_list_requests == [(0, 1)]
    assert notifier.employee_messages[0]["detail"] == "личная покупка"


async def test_apply_to_pay_does_not_notify_employee(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    expense = await _pending_expense(session, employee.id)
    settings = Settings()
    expenses = ExpensesRepo(session)
    await expenses.set_status(expense, ExpenseStatus.APPROVED)
    await session.commit()

    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.to_pay)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(55, webhook_status_name="К выплате")
    await session.commit()

    assert result is not None
    assert result.status is ExpenseStatus.TO_PAY
    assert notifier.employee_messages == []
    assert len(notifier.planfix_decision_marks) == 1


async def test_apply_approved_to_pay_to_reimbursed_chain(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    await _pending_expense(session, employee.id)
    settings = Settings()
    statuses = settings.planfix.statuses
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    service = _service(session, planfix, notifier)

    planfix.seed_task(55, status_id=statuses.approved)
    await service.apply(55)
    await session.commit()
    planfix.seed_task(55, status_id=statuses.to_pay)
    await service.apply(55)
    await session.commit()
    planfix.seed_task(55, status_id=statuses.reimbursed)
    await service.apply(55)
    await session.commit()

    expense = await ExpensesRepo(session).get_by_planfix_task_id(55)
    assert expense is not None
    assert expense.status is ExpenseStatus.REIMBURSED
    # Approved + reimbursed notify; to_pay does not.
    assert [m["status"] for m in notifier.employee_messages] == [
        ExpenseStatus.APPROVED,
        ExpenseStatus.REIMBURSED,
    ]


async def test_apply_unknown_status_id_is_noop(env: dict[str, str], session: AsyncSession) -> None:
    _, employee = await _people(session)
    await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=999_999)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(55)
    await session.commit()

    assert result is None
    expense = await ExpensesRepo(session).get_by_planfix_task_id(55)
    assert expense is not None
    assert expense.status is ExpenseStatus.PENDING
    assert notifier.employee_messages == []


async def test_apply_unknown_status_id_uses_name_only_as_hint(
    env: dict[str, str], session: AsyncSession
) -> None:
    _, employee = await _people(session)
    await _pending_expense(session, employee.id)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=999_999)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(
        55, webhook_status_name="Одобрено"
    )
    await session.commit()

    assert result is None
    # We still re-fetch by task id and rely on id mapping, not webhook body text.
    assert planfix.get_task_calls == 1
    assert notifier.employee_messages == []


async def test_apply_unknown_task_is_noop(env: dict[str, str], session: AsyncSession) -> None:
    settings = Settings()
    planfix = FakePlanfix()
    planfix.seed_task(99, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).apply(99)
    assert result is None
    assert notifier.employee_messages == []
