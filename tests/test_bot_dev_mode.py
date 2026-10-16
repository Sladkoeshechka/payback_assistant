# ruff: noqa: RUF001

import pytest
from aiogram import Bot
from conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import UserRole
from payback.db.repositories.users import UsersRepo


async def test_as_switches_role_only_when_dev_mode_enabled(
    env: dict[str, str],
    db_engine: AsyncEngine,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=UserRole.MANAGER,
    )
    await session.commit()

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    methods_before = len(telegram_session.methods)
    await dispatcher.feed_raw_update(bot, _message_update(1, manager.telegram_id, "/as employee"))
    assert len(telegram_session.methods) == methods_before
    await session.refresh(manager)
    assert manager.role.value == UserRole.MANAGER.value

    monkeypatch.setenv("DEV_MODE", "true")
    settings = Settings()
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(2, manager.telegram_id, "/as employee"))
    await session.refresh(manager)
    assert manager.role.value == UserRole.EMPLOYEE.value
    assert getattr(telegram_session.methods[-1], "text", None) == (
        "Роль переключена: сотрудник.\nМеню сотрудника: /my, /help"
    )

    telegram_id = manager.telegram_id
    await dispatcher.feed_raw_update(bot, _message_update(3, telegram_id, "/as manager"))
    session.expire_all()
    restored = await users.get_by_telegram_id(telegram_id)
    assert restored is not None
    assert restored.role == UserRole.MANAGER
    assert restored.manager_id is None


async def test_inactive_user_is_blocked_by_middleware(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    users = UsersRepo(session)
    employee = await users.create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
    )
    await users.set_active(employee, False)
    await session.commit()

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(1, 2, "/my"))
    assert getattr(telegram_session.methods[-1], "text", None) == (
        "Ваш доступ отключён. Обратитесь к руководителю."
    )


def _message_update(update_id: int, user_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "David"},
            "text": text,
            "entities": [{"offset": 0, "length": len(text.split()[0]), "type": "bot_command"}],
        },
    }
