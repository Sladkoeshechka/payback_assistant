from collections.abc import AsyncGenerator
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import TelegramMethod

from payback.bot.app import create_dispatcher
from payback.config import Settings


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[TelegramMethod[Any]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,
    ) -> Any:
        self.methods.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:
            yield b""

    async def close(self) -> None:
        pass


def test_create_dispatcher() -> None:
    dispatcher = create_dispatcher()
    assert isinstance(dispatcher.storage, MemoryStorage)


async def test_start_command(env: dict[str, str]) -> None:
    settings = Settings()

    session = RecordingSession()
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
    )

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

    assert session.methods[-1].text == "Введите имя и фамилию."

    raw_update["message"]["text"] = "David Martinez"

    raw_update["update_id"] = 10000001
    raw_update["message"]["message_id"] = 43
    raw_update["message"].pop("entities")

    await dispatcher.feed_raw_update(bot, raw_update)
