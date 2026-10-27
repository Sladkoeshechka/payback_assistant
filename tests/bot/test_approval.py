# ruff: noqa: RUF001

from datetime import date
from decimal import Decimal

from aiogram import Bot
from tests.conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot import texts
from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.fakes import FakeNotifier, FakePlanfix


async def test_manager_approve_callback(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, _, expense = await _pending_fixture(session, settings)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)
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
        bot, _callback_update(1, manager.telegram_id, f"mgr:approve:{expense.id}")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.APPROVED
    assert planfix.update_calls == 1
    assert notifier.cleared_keyboards == [(manager.id, 9001)]
    assert len(notifier.employee_messages) == 1
    assert any(
        type(method).__name__ == "AnswerCallbackQuery" for method in telegram_session.methods
    )


async def test_manager_cannot_approve_twice(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, _, expense = await _pending_fixture(session, settings)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)
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
        bot, _callback_update(1, manager.telegram_id, f"mgr:approve:{expense.id}")
    )
    await dispatcher.feed_raw_update(
        bot, _callback_update(2, manager.telegram_id, f"mgr:approve:{expense.id}")
    )

    assert planfix.update_calls == 1
    assert len(notifier.employee_messages) == 1
    assert any(
        getattr(method, "text", None) == texts.DECISION_ALREADY_TAKEN
        or getattr(method, "show_alert", False)
        for method in telegram_session.methods
    )


async def test_wrong_manager_cannot_approve(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, _, expense = await _pending_fixture(session, settings)
    stranger = await UsersRepo(session).create(
        telegram_id=99,
        first_name="Stranger",
        last_name="Manager",
        role=UserRole.MANAGER,
    )
    await session.commit()
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)
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
        bot, _callback_update(1, stranger.telegram_id, f"mgr:approve:{expense.id}")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.PENDING
    assert planfix.update_calls == 0
    assert notifier.employee_messages == []


async def test_reject_with_reason(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, _, expense = await _pending_fixture(session, settings)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.pending)
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
        bot, _callback_update(1, manager.telegram_id, f"mgr:reject:{expense.id}")
    )
    assert any(
        getattr(method, "text", None) == texts.ASK_REJECT_REASON
        for method in telegram_session.methods
    )
    await dispatcher.feed_raw_update(bot, _message_update(2, manager.telegram_id, "не по политике"))

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.REJECTED
    assert planfix.comments == [(55, "Grace Hopper:\nПричина отказа: не по политике", "user:7")]
    assert notifier.employee_messages[0]["detail"] == "не по политике"


async def test_manager_approve_rejected_when_planfix_already_changed(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, _, expense = await _pending_fixture(session, settings)
    planfix = FakePlanfix()
    planfix.seed_task(55, status_id=settings.planfix.statuses.to_pay)
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
        bot, _callback_update(1, manager.telegram_id, f"mgr:approve:{expense.id}")
    )

    await session.refresh(expense)
    assert expense.status is ExpenseStatus.TO_PAY
    assert planfix.update_calls == 0
    assert notifier.employee_messages == []
    assert any(
        getattr(method, "text", None) == texts.DECISION_ALREADY_TAKEN
        for method in telegram_session.methods
    )


async def _pending_fixture(session: AsyncSession, settings: Settings) -> tuple[User, User, Expense]:
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
    await expenses.set_status(expense, ExpenseStatus.PENDING)
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
            "from": {"id": user_id, "is_bot": False, "first_name": "Grace"},
            "text": text,
        },
    }


def _callback_update(update_id: int, user_id: int, data: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": str(update_id),
            "from": {"id": user_id, "is_bot": False, "first_name": "Grace"},
            "chat_instance": "test",
            "data": data,
            "message": {
                "message_id": update_id,
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 111, "is_bot": True, "first_name": "Payback"},
                "text": "Новая заявка",
            },
        },
    }
