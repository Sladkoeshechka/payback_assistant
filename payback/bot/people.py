from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from payback.bot.states import Registration


def create_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await state.set_state(Registration.waiting_for_name)
        await message.answer("Введите имя и фамилию.")

    @router.message(Registration.waiting_for_name)
    async def complete_registration(message: Message, state: FSMContext):
        print("Message received: ", message.text)
        await state.clear()

    return router
