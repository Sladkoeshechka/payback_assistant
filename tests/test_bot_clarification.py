
from datetime import date
from decimal import Decimal

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


async def test_employee_text_reply_returns_to_pending(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, employee, expense = await _clarification_fixture(session, settings)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(
        bot, _message_update(1, employee.telegram_id, "Приложил выписку")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.PENDING
    assert planfix.comments == [(55, "Приложил выписку")]
    assert planfix.task_updates[0][1] == {
        "status": {"id": settings.planfix.statuses.pending}
    }
    assert len(notifier.messages) == 1
    assert expense.manager_message_id == notifier.messages[0]["message_id"]
    assert any(
        getattr(method, "text", None) == texts.CLARIFICATION_REPLY_SENT
        for method in telegram_session.methods
    )
    del manager


async def test_employee_photo_reply_attaches_file(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee, expense = await _clarification_fixture(session, settings)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    telegram_session = RecordingSession(download_bytes=b"reply-bytes")
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(
        bot, _photo_update(1, employee.telegram_id, caption="скан")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.PENDING
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert planfix.comments == [(55, "скан")]
    assert notifier.messages[0]["has_image"] is True


async def test_photo_without_clarification_still_starts_submission(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    """Clarification router must SkipHandler so submission can claim the photo."""
    settings = Settings()
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
    await session.commit()

    planfix = FakePlanfix()
    notifier = FakeNotifier()
    telegram_session = RecordingSession(download_bytes=b"not-a-qr")
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(bot, _photo_update(1, employee.telegram_id))

    assert planfix.comment_calls == 0
    assert notifier.messages == []
    assert any(
        getattr(method, "text", None) is not None for method in telegram_session.methods
    )


async def _clarification_fixture(
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
    await expenses.set_status(expense, ExpenseStatus.CLARIFICATION)
    await expenses.set_manager_message(expense, 9001)
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


def _photo_update(
    update_id: int, user_id: int, *, caption: str | None = None
) -> dict[str, object]:
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


async def test_employee_text_reply_second_time(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee, expense = await _clarification_fixture(session, settings)
    planfix = FakePlanfix()
    notifier = FakeNotifier()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(
        bot, _message_update(1, employee.telegram_id, "Приложил выписку")
    )

    await dispatcher.feed_raw_update(
        bot, _message_update(2, employee.telegram_id, "Приложил выписку")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.PENDING
    assert planfix.comments == [(55, "Приложил выписку")]
    assert len(planfix.task_updates) == 1
    assert len(notifier.messages) == 1
    assert expense.manager_message_id == notifier.messages[0]["message_id"]
    assert len(telegram_session.methods) == 1
    assert getattr(telegram_session.methods[0], "text", None) == texts.CLARIFICATION_REPLY_SENT
