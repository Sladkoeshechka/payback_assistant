from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message


def create_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        print("I have received a message ", message.text)

    return router
