from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from payback.bot.states import Registration
from payback.config import Settings

from payback.db.repositories import UsersRepo
from payback.db.models.enums import UserRole

def create_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(message: Message, state: FSMContext, settings: Settings, users_repo: UsersRepo) -> None:
        if message.from_user.id == settings.owner_telegram_id:
            manager = await users_repo.get_by_telegram_id(telegram_id=message.from_user.id)
            if manager is None:
                await message.answer("Введите имя и фамилию.")
                await state.set_state(Registration.waiting_for_name)
            else:
                await message.answer("Вы уже зарегестрированы!.")
        else:
            await message.answer("Вы не владелец, приглашение сотрудников только по ссылке!")

    @router.message(Registration.waiting_for_name)
    async def complete_registration(message: Message, state: FSMContext, settings: Settings, users_repo: UsersRepo):
        first_name = message.text.split()[0]
        last_name = message.text.split()[1]
        manager = await users_repo.create(telegram_id=message.from_user.id,
            first_name=first_name, last_name=last_name, role=UserRole.MANAGER)
        await message.answer("Готово!")
        await state.clear()

    return router
