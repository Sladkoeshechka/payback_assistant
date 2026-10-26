from datetime import date
from decimal import Decimal
from pathlib import Path

from aiogram import Bot
from conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot import texts
from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.fakes import FakeNotifier, FakePlanfix

_RECEIPT = Path(__file__).parent / "fixtures" / "receipts" / "valid-receipt.jpg"


async def test_employee_text_reply_returns_to_approved(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee, expense = await _revision_fixture(session, settings)
    planfix = FakePlanfix()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=FakeNotifier(),
    )

    await dispatcher.feed_raw_update(
        bot, _message_update(1, employee.telegram_id, "Исправил документы")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.APPROVED
    assert planfix.comments == [(55, "Ada Lovelace:\nИсправил документы")]
    assert planfix.task_updates == [(55, {"status": {"id": settings.planfix.statuses.approved}})]
    assert any(
        getattr(method, "text", None) == texts.REVISION_REPLY_SENT
        for method in telegram_session.methods
    )


async def test_employee_revision_reply_second_time(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee, expense = await _revision_fixture(session, settings)
    planfix = FakePlanfix()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=FakeNotifier(),
    )

    await dispatcher.feed_raw_update(bot, _message_update(1, employee.telegram_id, "первый"))
    await dispatcher.feed_raw_update(bot, _message_update(2, employee.telegram_id, "второй"))

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.APPROVED
    assert len(planfix.comments) == 1
    assert len(planfix.task_updates) == 1
    assert (
        sum(
            1
            for method in telegram_session.methods
            if getattr(method, "text", None) == texts.REVISION_REPLY_SENT
        )
        == 1
    )


async def test_employee_revision_photo_reply(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee, expense = await _revision_fixture(session, settings)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    telegram_session = RecordingSession(download_bytes=_RECEIPT.read_bytes())
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(bot, _photo_update(1, employee.telegram_id, caption="скан"))

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.APPROVED
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert len(planfix.attachments) == 1
    file_id, task_id = planfix.attachments[0]
    assert task_id == 55
    assert planfix.files[file_id] == _RECEIPT.read_bytes()
    assert planfix.comments == [(55, "Ada Lovelace:\nскан")]
    assert len(notifier.messages) == 0


async def _revision_fixture(
    session: AsyncSession, settings: Settings
) -> tuple[User, User, Expense]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=settings.owner_telegram_id,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    expenses = ExpensesRepo(session)
    expense = await expenses.create_pending_submission(
        employee_id=employee.id,
        amount=Decimal("100.00"),
        purchase_date=date(2026, 10, 1),
        category_id=7,
        category_name="Материалы",
        no_receipt=True,
    )
    await expenses.set_planfix_task(expense, 55)
    await expenses.set_status(expense, ExpenseStatus.NEEDS_REVISION)
    await session.commit()
    return manager, employee, expense


def _message_update(update_id: int, user_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
            "text": text,
        },
    }


def _photo_update(update_id: int, user_id: int, *, caption: str | None = None) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": update_id,
        "date": 1_700_000_000,
        "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
        "photo": [
            {
                "file_id": "photo-file",
                "file_unique_id": "uniq",
                "width": 100,
                "height": 100,
            }
        ],
    }
    if caption is not None:
        message["caption"] = caption
    return {"update_id": update_id, "message": message}
