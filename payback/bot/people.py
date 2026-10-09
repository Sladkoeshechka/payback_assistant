"""Telegram handlers for registration and invitations."""

# ruff: noqa: RUF001

from datetime import UTC, datetime

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from payback.bot.keyboards import invite_role_keyboard
from payback.bot.states import EmployeeRegistration, OwnerRegistration
from payback.config import Settings
from payback.db.models.enums import UserRole
from payback.db.repositories import UsersRepo
from payback.db.repositories.invites import InvitesRepo
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
                await state.set_state(OwnerRegistration.waiting_for_name)
            else:
                await message.answer("Вы уже зарегистрированы.")
        else:
            await message.answer("Вы не владелец, приглашение сотрудников только по ссылке!")

    @router.message(OwnerRegistration.waiting_for_name)
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


def create_invite_router() -> Router:
    router = Router()

    @router.message(CommandStart(deep_link=True))
    async def cmd_start(
        message: types.Message,
        state: FSMContext,
        command: CommandObject,
        invites_repo: InvitesRepo,
    ) -> None:
        code = command.args
        if code is None:
            await message.answer("Эта ссылка невалидна.")
            return
        now = datetime.now(UTC)

        invite = await invites_repo.get_active_by_code(code=code, now=now)

        if invite is None:
            await message.answer("Эта ссылка невалидна.")
            return

        await state.update_data(invite_code=code)

        await message.answer(
            f"Инвайт подтвержден! Ваша роль: {invite.role.value}. Введите ваше имя:"
        )
        await state.set_state(EmployeeRegistration.waiting_for_name)

    @router.message(EmployeeRegistration.waiting_for_name)
    async def complete_registration(
        message: Message,
        state: FSMContext,
        users_repo: UsersRepo,
        invites_repo: InvitesRepo,
        bot: Bot,
    ) -> None:
        if message.from_user is None or message.text is None:
            return
        name = message.text.split(maxsplit=1)
        if len(name) != 2:
            await message.answer("Введите имя и фамилию через пробел.")
            return

        invite_code = (await state.get_data()).get("invite_code")
        if not isinstance(invite_code, str):
            await state.clear()
            await message.answer("Эта ссылка невалидна.")
            return
        now = datetime.now(UTC)
        invite = await invites_repo.get_active_by_code(code=invite_code, now=now)
        if invite is None:
            await state.clear()
            await message.answer("Эта ссылка невалидна.")
            return

        user = await users_repo.create(
            telegram_id=message.from_user.id,
            first_name=name[0],
            last_name=name[1],
            role=invite.role,
            manager_id=invite.created_by_id if invite.role == UserRole.EMPLOYEE else None,
        )

        await invites_repo.consume(invite=invite, user_id=user.id, used_at=now)

        # TODO: add menu
        if user.role == UserRole.EMPLOYEE:
            await message.answer("Добро пожаловать! Вы зарегистрированы как сотрудник.")
        else:
            await message.answer("Добро пожаловать! Вы зарегистрированы как руководитель.")

        creator = await users_repo.get_by_id(invite.created_by_id)

        if creator:
            try:
                full_name = f"{name[0]} {name[1]}"
                notification = (
                    f"🔔 По вашей ссылке ({invite.code}) "
                    "зарегистрировался новый пользователь:\n"
                    f"👤 {full_name} (Роль: {invite.role.value})"
                )
                await bot.send_message(chat_id=creator.telegram_id, text=notification)
            except Exception as error:
                print(f"Could not notify creator {creator.telegram_id}: {error}")

        await state.clear()

    return router
