"""Telegram handlers for registration and invitations."""

# ruff: noqa: RUF001

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from payback.bot.keyboards import invite_role_keyboard
from payback.bot.states import Registration
from payback.config import Settings
from payback.db.models.enums import UserRole
from payback.db.repositories import UsersRepo
from payback.services.people import ManagerRequiredError, PeopleService


def create_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(
        message: Message, state: FSMContext, settings: Settings, users_repo: UsersRepo
    ) -> None:
        if message.from_user is None:
            return
        if message.from_user.id == settings.owner_telegram_id:
            manager = await users_repo.get_by_telegram_id(telegram_id=message.from_user.id)
            if manager is None:
                await message.answer("Введите имя и фамилию.")
                await state.set_state(Registration.waiting_for_name)
            else:
                await message.answer("Вы уже зарегистрированы.")
        else:
            await message.answer("Вы не владелец, приглашение сотрудников только по ссылке!")

    @router.message(Registration.waiting_for_name)
    async def complete_registration(
        message: Message, state: FSMContext, users_repo: UsersRepo
    ) -> None:
        if message.from_user is None or message.text is None:
            return
        name = message.text.split(maxsplit=1)
        if len(name) != 2:
            await message.answer("Введите имя и фамилию через пробел.")
            return
        await users_repo.create(
            telegram_id=message.from_user.id,
            first_name=name[0],
            last_name=name[1],
            role=UserRole.MANAGER,
        )
        await message.answer("Готово!")
        await state.clear()

    @router.message(Command("invite"))
    async def invite(message: Message, people: PeopleService) -> None:
        if message.from_user is None:
            return
        try:
            await people.verify_manager(message.from_user.id)
        except ManagerRequiredError:
            await message.answer("Эта команда доступна только руководителям.")
            return
        await message.answer("Кого вы хотите пригласить?", reply_markup=invite_role_keyboard())

    @router.callback_query(F.data.in_({"invite:employee", "invite:manager"}))
    async def choose_invite_role(callback: CallbackQuery, people: PeopleService, bot: Bot) -> None:
        if callback.data is None or callback.message is None or callback.from_user is None:
            return
        role = UserRole(callback.data.rsplit(":", 1)[1])
        try:
            invite = await people.create_invite(callback.from_user.id, role)
        except ManagerRequiredError:
            await callback.answer("Эта команда доступна только руководителям.", show_alert=True)
            return

        me = await bot.get_me()
        if me.username is None:
            raise RuntimeError("Telegram bot must have a username to create invitation links")
        link = f"https://t.me/{me.username}?start={invite.code}"
        await callback.message.answer(
            f"Приглашение создано: {link}\nОно действует 72 часа и используется один раз."
        )
        await callback.answer()

    return router
