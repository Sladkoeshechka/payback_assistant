# ruff: noqa: RUF001

from datetime import UTC, datetime, timedelta

from aiogram import Bot
from conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import Invite, UserRole
from payback.db.repositories.invites import InvitesRepo
from payback.db.repositories.users import UsersRepo


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
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    dispatcher = create_dispatcher(settings, session_factory)

    await dispatcher.feed_raw_update(bot, _message_update(1, settings.owner_telegram_id, "/invite"))
    invite_prompt = telegram_session.methods[-1]
    assert getattr(invite_prompt, "text", None) == "Кого вы хотите пригласить?"
    assert getattr(invite_prompt, "reply_markup", None) is not None

    await dispatcher.feed_raw_update(
        bot, _callback_update(2, settings.owner_telegram_id, "invite:employee")
    )

    saved_invite = await _only_invite(session)
    assert saved_invite.role == UserRole.EMPLOYEE
    assert saved_invite.created_by_id == manager.id
    assert saved_invite.code
    now = datetime.now(UTC)
    expires_at = saved_invite.expires_at.replace(tzinfo=UTC)
    assert now + timedelta(hours=71) < expires_at <= now + timedelta(hours=73)
    sent_text = getattr(telegram_session.methods[-2], "text", None)
    assert sent_text is not None
    assert f"https://t.me/payback_test_bot?start={saved_invite.code}" in sent_text


async def _only_invite(session: AsyncSession) -> Invite:
    invites = await InvitesRepo(session).list_active_for_creator(1, datetime.now(UTC))
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


async def test_user_receives_invite(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:

    employee_user_id = 2
    employee_user_role = UserRole.EMPLOYEE

    settings = Settings()
    manager = await UsersRepo(session).create(
        telegram_id=settings.owner_telegram_id,
        first_name="David",
        last_name="Martinez",
        role=employee_user_role,
    )

    invite = await InvitesRepo(session).create(
        code="employee-invite",
        role=employee_user_role,
        created_by_id=manager.id,
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )

    await session.commit()

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    dispatcher = create_dispatcher(settings, session_factory)

    await dispatcher.feed_raw_update(
        bot, _message_update(1, employee_user_id, f"/start {invite.code}")
    )

    invite_prompt = telegram_session.methods[-1]
    assert (
        getattr(invite_prompt, "text", None)
        == f"Инвайт подтвержден! Ваша роль: {invite.role.value}. Введите ваше имя:"
    )

    await dispatcher.feed_raw_update(bot, _message_update(2, employee_user_id, "Martin Josef"))

    employee_user = await UsersRepo(session).get_by_telegram_id(telegram_id=employee_user_id)

    assert employee_user is not None
    assert employee_user.role == employee_user_role
    assert employee_user.manager_id == manager.id

    saved_invite = await InvitesRepo(session).get_by_code(invite.code)
    assert saved_invite is not None
    assert saved_invite.used_by_id == employee_user.id
    assert saved_invite.used_at is not None

    notifications = [getattr(method, "text", None) for method in telegram_session.methods]
    assert any(
        text is not None and "Martin Josef" in text and "employee" in text for text in notifications
    )

    active_invites = await InvitesRepo(session).list_active_for_creator(
        creator_id=manager.id, now=datetime.now(UTC)
    )
    assert active_invites == []

    await dispatcher.feed_raw_update(
        bot, _message_update(3, employee_user_id, f"/start {invite.code}")
    )

    invite_prompt = telegram_session.methods[-1]
    assert getattr(invite_prompt, "text", None) == "Эта ссылка невалидна."
