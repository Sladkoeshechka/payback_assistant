# ruff: noqa: RUF001

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from aiogram import Bot
from conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import ExpenseStatus, Invite, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.invites import InvitesRepo
from payback.db.repositories.users import UsersRepo
from payback.planfix.directories import DirectoryCache
from payback.planfix.models import PlanfixUser


class FakePlanfix:
    def __init__(self, users: list[PlanfixUser] | None = None) -> None:
        self.users = users or [
            PlanfixUser(id=3, name="Руководитель", last_name="Тест"),
            PlanfixUser(id=7, name="payback", last_name="robot"),
        ]

    async def list_users(self) -> list[PlanfixUser]:
        return list(self.users)


class _UnusedPlanfixClient:
    """DirectoryCache only needs a client for fetches; /refresh only invalidates."""


async def test_staff_lists_people_and_revokes_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, employee, invite = await _staff_fixture(session, settings)
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=FakePlanfix(),
    )

    await dispatcher.feed_raw_update(bot, _message_update(1, manager.telegram_id, "/staff"))
    staff_text = getattr(telegram_session.methods[-1], "text", None)
    assert staff_text is not None
    assert "Ada Lovelace" in staff_text
    assert "сотрудник" in staff_text
    assert "не связан" in staff_text

    await dispatcher.feed_raw_update(
        bot, _callback_update(2, manager.telegram_id, f"staff:revoke:{invite.id}")
    )
    saved = await InvitesRepo(session).get_by_id(invite.id)
    assert saved is not None
    assert saved.revoked_at is not None
    assert employee.is_active is True


async def test_staff_deactivates_employee_and_links_planfix(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, employee, _ = await _staff_fixture(session, settings)
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=FakePlanfix(),
    )

    await dispatcher.feed_raw_update(
        bot, _callback_update(1, manager.telegram_id, f"staff:off:{employee.id}")
    )
    await session.refresh(employee)
    assert employee.is_active is False

    await dispatcher.feed_raw_update(bot, _callback_update(2, manager.telegram_id, "staff:link"))
    assert getattr(telegram_session.methods[-2], "text", None) == (
        "Выберите своего пользователя в ПланФиксе:"
    )

    await dispatcher.feed_raw_update(bot, _callback_update(3, manager.telegram_id, "staff:pf:3"))
    await session.refresh(manager)
    assert manager.planfix_user_id == 3
    assert any(
        getattr(method, "text", None) == "ПланФикс связан: пользователь #3."
        for method in telegram_session.methods
    )


async def test_help_refresh_my_and_pending(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager = await UsersRepo(session).create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=UserRole.MANAGER,
    )
    employee = await UsersRepo(session).create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    expenses = ExpensesRepo(session)
    mine = await expenses.create_pending_submission(
        employee_id=employee.id,
        amount=Decimal("1250.00"),
        purchase_date=date(2026, 9, 28),
        category_id=7,
        category_name="Материалы",
        no_receipt=False,
    )
    await expenses.set_status(mine, ExpenseStatus.PENDING)
    await expenses.set_planfix_task(mine, 35)
    await session.commit()

    from payback.planfix.directories import _CachedDirectory
    from payback.planfix.models import PlanfixDirectoryEntry

    cache = DirectoryCache(_UnusedPlanfixClient())  # type: ignore[arg-type]
    cache._cached[11176] = _CachedDirectory(
        loaded_at=0.0,
        entries=(PlanfixDirectoryEntry(key=7, name="Материалы"),),
    )

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        directory_cache=cache,
    )

    await dispatcher.feed_raw_update(bot, _message_update(1, manager.telegram_id, "/help"))
    assert "Справка руководителя" in getattr(telegram_session.methods[-1], "text", "")

    await dispatcher.feed_raw_update(bot, _message_update(2, manager.telegram_id, "/refresh"))
    assert getattr(telegram_session.methods[-1], "text", None) == "Кэш справочников сброшен."
    assert cache._cached == {}

    await dispatcher.feed_raw_update(bot, _message_update(3, employee.telegram_id, "/my"))
    my_text = getattr(telegram_session.methods[-1], "text", None)
    assert my_text is not None
    assert "№35" in my_text
    assert "На согласовании" in my_text

    await dispatcher.feed_raw_update(bot, _message_update(4, manager.telegram_id, "/pending"))
    pending_text = getattr(telegram_session.methods[-1], "text", None)
    assert pending_text is not None
    assert "Ada Lovelace" in pending_text
    assert "1 250,00 ₽" in pending_text


async def test_employee_cannot_use_manager_commands(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    await UsersRepo(session).create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
    )
    await session.commit()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    for update_id, command in enumerate(("/staff", "/pending", "/refresh"), start=1):
        await dispatcher.feed_raw_update(bot, _message_update(update_id, 2, command))
        assert getattr(telegram_session.methods[-1], "text", None) == (
            "Эта команда доступна только руководителям."
        )


async def _staff_fixture(
    session: AsyncSession, settings: Settings
) -> tuple[User, User, Invite]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    invite = await InvitesRepo(session).create(
        code="active-invite",
        role=UserRole.EMPLOYEE,
        created_by_id=manager.id,
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    await session.commit()
    return manager, employee, invite


def _message_update(update_id: int, user_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "David"},
            "text": text,
            "entities": [{"offset": 0, "length": len(text), "type": "bot_command"}],
        },
    }


def _callback_update(update_id: int, user_id: int, data: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": str(update_id),
            "from": {"id": user_id, "is_bot": False, "first_name": "David"},
            "chat_instance": "test",
            "data": data,
            "message": {
                "message_id": update_id,
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 111, "is_bot": True, "first_name": "Payback"},
                "text": "Управление командой",
            },
        },
    }
