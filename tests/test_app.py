from aiogram.fsm.storage.memory import MemoryStorage

from payback.bot.app import create_bot, create_dispatcher
from payback.config import Settings


def test_create_dispatcher() -> None:
    dispatcher = create_dispatcher()
    assert isinstance(dispatcher.storage, MemoryStorage)


async def test_start_command(env: dict[str, str]) -> None:
    settings = Settings()

    bot = create_bot(settings)
    dispatcher = create_dispatcher()

    raw_update = {
        "update_id": 10000000,
        "message": {
            "message_id": 42,
            "date": 1672531200,
            "chat": {
                "id": 987654321,
                "type": "private",
                "first_name": "Test",
                "username": "test_user",
            },
            "from": {
                "id": 987654321,
                "is_bot": False,
                "first_name": "Test",
                "username": "test_user",
                "language_code": "ru",
            },
            "text": "/start",  # Наша команда
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }

    await dispatcher.feed_raw_update(bot=bot, update=raw_update)
