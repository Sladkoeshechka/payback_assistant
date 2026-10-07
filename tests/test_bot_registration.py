from copy import deepcopy
from typing import Any

from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage
from conftest import RecordingSession
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.repositories.users import UsersRepo


def test_create_dispatcher(env: dict[str, str], db_engine: AsyncEngine) -> None:
    settings = Settings()

    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )

    dispatcher = create_dispatcher(settings, session_factory)
    assert isinstance(dispatcher.storage, MemoryStorage)


async def test_manager_registration(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()

    telegram_session = RecordingSession()
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=telegram_session,
    )

    session_factory = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
    )

    dispatcher = create_dispatcher(settings, session_factory)

    raw_update: dict[str, Any] = {
        "update_id": 10000000,
        "message": {
            "message_id": 42,
            "date": 1672531200,
            "chat": {
                "id": 987654321,
                "type": "private",
                "first_name": "Test",
                "username": "test_manager",
            },
            "from": {
                "id": settings.owner_telegram_id,
                "is_bot": False,
                "first_name": "David",
                "username": "test_manager",
                "language_code": "ru",
            },
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }

    await dispatcher.feed_raw_update(bot=bot, update=raw_update)

    assert getattr(telegram_session.methods[-1], "text", None) == "Введите имя и фамилию."

    new_update = deepcopy(raw_update)
    new_update["message"]["text"] = "David Martinez"
    new_update["update_id"] = raw_update["update_id"] + 1
    new_update["message"]["message_id"] = 43
    new_update["message"].pop("entities")

    await dispatcher.feed_raw_update(bot, new_update)

    assert getattr(telegram_session.methods[-1], "text", None) == "Готово!"

    await dispatcher.feed_raw_update(bot, raw_update)

    assert getattr(telegram_session.methods[-1], "text", None) == "Вы уже зарегистрированы."

    unknown_update = deepcopy(raw_update)
    unknown_update["message"]["from"]["id"] = 10234

    await dispatcher.feed_raw_update(bot, unknown_update)

    assert (
        getattr(telegram_session.methods[-1], "text", None)
        == "Вы не владелец, приглашение сотрудников только по ссылке!"
    )

    user = UsersRepo(session)

    manager = await user.get_by_telegram_id(telegram_id=settings.owner_telegram_id)

    assert manager is not None
    assert manager.first_name == "David"
    assert manager.last_name == "Martinez"
