from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.clarification import ClarificationService, NoClarificationPendingError
from payback.services.fakes import FakeNotifier, FakePlanfix


async def _people(session: AsyncSession) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=2000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=2001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, employee


async def _clarification_expense(session: AsyncSession, employee_id: int) -> Expense:
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
    await expenses.set_status(expense, ExpenseStatus.CLARIFICATION)
    await expenses.set_manager_message(expense, 9001)
    await session.commit()
    return expense


def _service(
    session: AsyncSession, planfix: FakePlanfix, notifier: FakeNotifier
) -> ClarificationService:
    return ClarificationService(
        ExpensesRepo(session),
        planfix,
        notifier,
        Settings().planfix.statuses,
    )


async def test_reply_text_moves_to_pending_and_renotifies(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    expense = await _clarification_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    settings = Settings()

    result = await _service(session, planfix, notifier).reply(
        employee=employee, manager=manager, text="Вот чек из почты"
    )
    await session.commit()

    assert result.status is ExpenseStatus.PENDING
    assert planfix.comments == [(55, "Вот чек из почты")]
    assert planfix.task_updates == [(55, {"status": {"id": settings.planfix.statuses.pending}})]
    assert planfix.upload_calls == 0
    assert len(notifier.messages) == 1
    assert notifier.messages[0]["expense_id"] == expense.id
    assert notifier.messages[0]["reply_text"] == "Вот чек из почты"
    assert notifier.cleared_keyboards == [(manager.id, 9001)]
    assert result.manager_message_id == notifier.messages[0]["message_id"]
    assert result.manager_message_id != 9001


async def test_reply_photo_uploads_and_attaches(env: dict[str, str], session: AsyncSession) -> None:
    manager, employee = await _people(session)
    await _clarification_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()

    result = await _service(session, planfix, notifier).reply(
        employee=employee,
        manager=manager,
        text="Скан",
        image_bytes=b"fake-image",
        image_filename="scan.jpg",
        image_content_type="image/jpeg",
    )
    await session.commit()

    assert result.status is ExpenseStatus.PENDING
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert planfix.attachments == [(1000, 55)]
    assert planfix.comments == [(55, "Скан")]
    assert notifier.cleared_keyboards == [(manager.id, 9001)]
    assert notifier.messages[0]["has_image"] is True
    assert notifier.messages[0]["reply_text"] == "Скан"


async def test_reply_photo_without_caption_uses_default_comment(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    await _clarification_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()

    await _service(session, planfix, notifier).reply(
        employee=employee,
        manager=manager,
        image_bytes=b"fake-image",
    )
    await session.commit()

    assert planfix.comments == [(55, "Ответ сотрудника (фото)")]


async def test_reply_when_not_clarification_raises(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    planfix = FakePlanfix()
    notifier = FakeNotifier()

    with pytest.raises(NoClarificationPendingError):
        await _service(session, planfix, notifier).reply(
            employee=employee, manager=manager, text="поздно"
        )
    assert planfix.comment_calls == 0
    assert notifier.messages == []


async def test_second_reply_rejected_when_already_pending(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    await _clarification_expense(session, employee.id)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    service = _service(session, planfix, notifier)

    await service.reply(employee=employee, manager=manager, text="первый")
    await session.commit()

    with pytest.raises(NoClarificationPendingError):
        await service.reply(employee=employee, manager=manager, text="второй")
    assert planfix.comment_calls == 1
    assert len(notifier.messages) == 1
