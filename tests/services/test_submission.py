# ruff: noqa: RUF001

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payback.config import Settings
from payback.db.models import ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.draft import SubmissionDraft
from payback.services.expense_card import custom_field_data_for_draft, task_name
from payback.services.fakes import FakeNotifier, FakePlanfix
from payback.services.submission import DuplicateReceiptError, SubmissionService


async def _people(session: AsyncSession) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    await users.link_planfix_user(manager, 3)
    employee = await users.create(
        telegram_id=1001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, employee


def _draft(**overrides: object) -> SubmissionDraft:
    values: dict[str, object] = {
        "amount": Decimal("1250.00"),
        "purchase_date": date(2026, 9, 28),
        "category_id": 7,
        "category_name": "Материалы",
        "no_receipt": False,
        "direction_id": 2,
        "direction_name": "Ленина 5",
        "comment": "Саморезы",
        "fn": "9282440300671549",
        "fd": "12345",
        "fp": "67890",
        "telegram_file_id": "tg-file-1",
        "image_bytes": b"jpeg-bytes",
        "qr_locked": True,
    }
    values.update(overrides)
    return SubmissionDraft(**values)  # type: ignore[arg-type]


def _service(
    session: AsyncSession, planfix: FakePlanfix, notifier: FakeNotifier
) -> SubmissionService:
    settings = Settings()
    return SubmissionService(
        ExpensesRepo(session),
        planfix,
        notifier,
        settings.planfix.fields,
    )


async def test_submit_happy_path_creates_task_file_and_notifies(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    service = _service(session, planfix, notifier)

    expense = await service.submit(_draft(), employee=employee, manager=manager)
    await session.commit()

    assert expense.status is ExpenseStatus.PENDING
    assert expense.planfix_task_id == 100
    assert expense.planfix_file_id == 1000
    assert expense.manager_message_id == 5000
    assert planfix.create_calls == 1
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert len(notifier.messages) == 1


async def test_submit_without_image_skips_file_steps(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    service = _service(session, planfix, notifier)

    expense = await service.submit(
        _draft(no_receipt=True, fn=None, fd=None, fp=None, image_bytes=None),
        employee=employee,
        manager=manager,
    )

    assert expense.status is ExpenseStatus.PENDING
    assert expense.planfix_task_id == 100
    assert expense.planfix_file_id is None
    assert planfix.upload_calls == 0
    assert planfix.attach_calls == 0


@pytest.mark.parametrize("fail_on", ["create_task", "upload_file", "attach_file"])
async def test_resume_after_planfix_step_failure(
    env: dict[str, str], session: AsyncSession, fail_on: str
) -> None:
    manager, employee = await _people(session)
    failing = FakePlanfix(fail_on=fail_on)
    notifier = FakeNotifier()
    service = _service(session, failing, notifier)
    draft = _draft()

    partial = await service.submit(draft, employee=employee, manager=manager)
    await session.commit()

    expenses = ExpensesRepo(session)
    existing = await expenses.get_by_fiscal_data("9282440300671549", "12345", "67890")
    assert existing is not None
    assert existing.id == partial.id
    assert existing.status is ExpenseStatus.PENDING_SUBMISSION

    if fail_on == "create_task":
        assert existing.planfix_task_id is None
    elif fail_on == "upload_file":
        assert existing.planfix_task_id is not None
        assert existing.planfix_file_id is None
    else:
        assert existing.planfix_file_id is not None

    healthy = FakePlanfix()
    # Keep task/file id sequences compatible with already stored ids when resuming
    if existing.planfix_task_id is not None:
        healthy.tasks_by_expense[existing.id] = existing.planfix_task_id
        healthy._next_task_id = existing.planfix_task_id + 1
    if existing.planfix_file_id is not None:
        healthy.files[existing.planfix_file_id] = draft.image_bytes or b""
        healthy._next_file_id = existing.planfix_file_id + 1

    resumed = await SubmissionService(
        expenses, healthy, notifier, Settings().planfix.fields
    ).resume(
        existing,
        employee=employee,
        manager=manager,
        image_bytes=draft.image_bytes,
    )
    await session.commit()

    assert resumed.status is ExpenseStatus.PENDING
    assert resumed.planfix_task_id is not None
    assert resumed.planfix_file_id is not None
    assert resumed.manager_message_id is not None
    assert healthy.create_calls == (1 if fail_on == "create_task" else 0)
    assert healthy.upload_calls == (0 if fail_on == "attach_file" else 1)
    assert healthy.attach_calls == 1


async def test_duplicate_fiscal_receipt_is_rejected(
    env: dict[str, str], session: AsyncSession
) -> None:
    manager, employee = await _people(session)
    service = _service(session, FakePlanfix(), FakeNotifier())
    first = await service.submit(_draft(), employee=employee, manager=manager)
    await session.commit()

    with pytest.raises(DuplicateReceiptError) as raised:
        await service.submit(_draft(), employee=employee, manager=manager)

    message = str(raised.value)
    assert "Этот чек уже подан" in message
    assert f"№{first.planfix_task_id}" in message
    assert "На согласовании" in message


async def test_expense_card_payload_and_task_name(env: dict[str, str]) -> None:
    settings = Settings()
    draft = _draft()
    assert draft.amount is not None
    assert draft.category_name is not None

    assert (
        task_name(
            amount=draft.amount,
            category_name=draft.category_name,
            employee_name="Ada Lovelace",
        )
        == "Расход: 1 250,00 ₽, Материалы — Ada Lovelace"
    )

    payload = custom_field_data_for_draft(
        draft, employee_name="Ada Lovelace", field_ids=settings.planfix.fields
    )
    by_id = {
        item["field"]["id"]: item["value"]  # type: ignore[index]
        for item in payload
    }
    assert by_id[settings.planfix.fields.amount] == 1250.0
    assert by_id[settings.planfix.fields.purchase_date] == {"date": "28-09-2026"}
    assert by_id[settings.planfix.fields.category] == {"id": 7}
    assert by_id[settings.planfix.fields.direction] == {"id": 2}
    assert by_id[settings.planfix.fields.employee] == "Ada Lovelace"
    assert by_id[settings.planfix.fields.fn] == "9282440300671549"
    assert by_id[settings.planfix.fields.no_receipt] is False
    assert settings.planfix.fields.payment_date not in by_id


async def test_create_task_without_assignee_when_manager_unlinked(
    env: dict[str, str], session: AsyncSession
) -> None:
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

    planfix = FakePlanfix()
    service = _service(session, planfix, FakeNotifier())
    expense = await service.submit(
        _draft(fn=None, fd=None, fp=None),
        employee=employee,
        manager=manager,
    )

    assert expense.planfix_task_id == 100
    assert expense.status is ExpenseStatus.PENDING
