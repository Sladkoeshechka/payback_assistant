# ruff: noqa: RUF001

from datetime import UTC, datetime, timedelta

import pytest
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import Invite, User, UserRole
from payback.db.repositories.invites import InvitesRepo
from payback.db.repositories.users import UsersRepo
from tests.conftest import RecordingSession


async def test_manager_creates_employee_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager = await UsersRepo(session).create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=UserRole.MANAGER,
    )
    await session.commit()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(1, settings.owner_telegram_id, "/invite"))
    invite_prompt = telegram_session.methods[-1]
    assert getattr(invite_prompt, "text", None) == "Кого вы хотите пригласить?"
    assert getattr(invite_prompt, "reply_markup", None) is not None

    await dispatcher.feed_raw_update(
        bot, _callback_update(2, settings.owner_telegram_id, "invite:employee")
    )

    saved_invite = await _only_invite(session, manager.id)
    assert saved_invite.role == UserRole.EMPLOYEE
    assert saved_invite.created_by_id == manager.id
    assert saved_invite.code
    now = datetime.now(UTC)
    expires_at = saved_invite.expires_at.replace(tzinfo=UTC)
    assert now + timedelta(hours=71) < expires_at <= now + timedelta(hours=73)
    sent_text = getattr(telegram_session.methods[-2], "text", None)
    assert sent_text is not None
    assert f"https://t.me/payback_test_bot?start={saved_invite.code}" in sent_text


async def test_employee_registers_from_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, invite = await _manager_and_invite(session, settings, UserRole.EMPLOYEE)
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    employee_telegram_id = 2
    await dispatcher.feed_raw_update(
        bot, _message_update(1, employee_telegram_id, f"/start {invite.code}")
    )
    assert getattr(telegram_session.methods[-1], "text", None) == "Введите имя и фамилию."

    await dispatcher.feed_raw_update(bot, _message_update(2, employee_telegram_id, "Martin Josef"))

    employee = await UsersRepo(session).get_by_telegram_id(employee_telegram_id)
    assert employee is not None
    assert employee.role == UserRole.EMPLOYEE
    assert employee.manager_id == manager.id

    saved_invite = await InvitesRepo(session).get_by_code(invite.code)
    assert saved_invite is not None
    assert saved_invite.used_by_id == employee.id
    assert saved_invite.used_at is not None
    assert any(
        text is not None and "Martin Josef" in text and "сотрудник" in text
        for text in (getattr(method, "text", None) for method in telegram_session.methods)
    )

    await dispatcher.feed_raw_update(
        bot, _message_update(3, employee_telegram_id, f"/start {invite.code}")
    )
    assert getattr(telegram_session.methods[-1], "text", None) == (
        "Вы уже зарегистрированы.\nМеню сотрудника: /my, /noreceipt, /help"
    )


async def test_manager_registers_from_manager_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, invite = await _manager_and_invite(session, settings, UserRole.MANAGER)
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    manager_telegram_id = 2
    await dispatcher.feed_raw_update(
        bot, _message_update(1, manager_telegram_id, f"/start {invite.code}")
    )
    await dispatcher.feed_raw_update(bot, _message_update(2, manager_telegram_id, "Maria Smith"))

    manager = await UsersRepo(session).get_by_telegram_id(manager_telegram_id)
    assert manager is not None
    assert manager.role == UserRole.MANAGER
    assert manager.manager_id is None


async def test_existing_manager_cannot_consume_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, invite = await _manager_and_invite(session, settings, UserRole.EMPLOYEE)
    existing_manager = await UsersRepo(session).create(
        telegram_id=2,
        first_name="Maria",
        last_name="Smith",
        role=UserRole.MANAGER,
    )
    await session.commit()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(1, 2, f"/start {invite.code}"))

    assert getattr(telegram_session.methods[-1], "text", None) == (
        "Вы уже зарегистрированы.\nМеню руководителя: /invite, /staff, /pending, /refresh, /help"
    )
    saved_invite = await InvitesRepo(session).get_by_code(invite.code)
    assert saved_invite is not None
    assert saved_invite.used_at is None
    assert existing_manager.role == UserRole.MANAGER


@pytest.mark.parametrize("code", ["missing", "expired-invite"])
async def test_invalid_or_expired_invite_is_rejected(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession, code: str
) -> None:
    settings = Settings()
    if code == "expired-invite":
        manager, _ = await _manager_and_invite(session, settings, UserRole.EMPLOYEE)
        expired = await InvitesRepo(session).create(
            code=code,
            role=UserRole.EMPLOYEE,
            created_by_id=manager.id,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert expired.code == code
        await session.commit()

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(1, 2, f"/start {code}"))

    assert (
        getattr(telegram_session.methods[-1], "text", None)
        == "Эта ссылка недействительна, уже использована или истекла."
    )
    assert await UsersRepo(session).get_by_telegram_id(2) is None


async def _manager_and_invite(
    session: AsyncSession, settings: Settings, invite_role: UserRole
) -> tuple[User, Invite]:
    manager = await UsersRepo(session).create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=UserRole.MANAGER,
    )
    invite = await InvitesRepo(session).create(
        code=f"{invite_role.value}-invite",
        role=invite_role,
        created_by_id=manager.id,
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )
    await session.commit()
    return manager, invite


async def _only_invite(session: AsyncSession, manager_id: int) -> Invite:
    invites = await InvitesRepo(session).list_active_for_creator(manager_id, datetime.now(UTC))
    assert len(invites) == 1
    return invites[0]


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
                "text": "Кого вы хотите пригласить?",
            },
        },
    }
