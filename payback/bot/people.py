"""Telegram handlers for registration and invitations."""

# ruff: noqa: RUF001

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from payback.bot import texts
from payback.bot.keyboards import invite_role_keyboard
from payback.bot.states import EmployeeRegistration, OwnerRegistration
from payback.config import Settings
from payback.db.models.enums import UserRole
from payback.db.repositories import UsersRepo
from payback.services.people import (
    AlreadyRegisteredError,
    InvitedRegistration,
    InviteUnavailableError,
    ManagerRequiredError,
    PeopleService,
)

logger = logging.getLogger(__name__)


def create_router() -> Router:
    router = Router()

    @router.message(Command("start"))
    async def cmd_start(
        message: Message, state: FSMContext, settings: Settings, users_repo: UsersRepo
    ) -> None:
        if message.from_user is None:
            return
        logger.debug(
            "received start command",
            extra={
                "telegram_user_id": message.from_user.id,
                "telegram_chat_id": message.chat.id,
            },
        )
        user = await users_repo.get_by_telegram_id(message.from_user.id)
        if user is not None:
            await state.clear()
            if not user.is_active:
                await message.answer(texts.INACTIVE_USER)
                return
            await message.answer(f"{texts.ALREADY_REGISTERED}\n{texts.menu(user.role)}")
            return
        if message.from_user.id != settings.owner_telegram_id:
            await message.answer(texts.UNKNOWN_START)
            return
        await message.answer(texts.ASK_NAME)
        await state.set_state(OwnerRegistration.waiting_for_name)

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
            await message.answer(texts.MANAGER_ONLY)
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
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
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
    """Create handlers for entering and completing invitation-based registration."""
    router = Router()

    @router.message(CommandStart(deep_link=True))
    async def start_from_invite(
        message: Message,
        state: FSMContext,
        command: CommandObject,
        people: PeopleService,
        users_repo: UsersRepo,
    ) -> None:
        if message.from_user is None or command.args is None:
            await message.answer(texts.INVALID_INVITE)
            return
        existing_user = await users_repo.get_by_telegram_id(message.from_user.id)
        if existing_user is not None:
            await state.clear()
            if not existing_user.is_active:
                await message.answer(texts.INACTIVE_USER)
                return
            await message.answer(f"{texts.ALREADY_REGISTERED}\n{texts.menu(existing_user.role)}")
            return
        try:
            invite = await people.start_invited_registration(message.from_user.id, command.args)
        except AlreadyRegisteredError:
            await state.clear()
            await message.answer(texts.ALREADY_REGISTERED)
            return
        except InviteUnavailableError:
            await state.clear()
            await message.answer(texts.INVALID_INVITE)
            return

        await state.set_state(EmployeeRegistration.waiting_for_name)
        await state.update_data(invite_code=invite.code)
        await message.answer(texts.ASK_NAME)

    @router.message(EmployeeRegistration.waiting_for_name)
    async def complete_invited_registration(
        message: Message,
        state: FSMContext,
        people: PeopleService,
        bot: Bot,
    ) -> None:
        if message.from_user is None or message.text is None:
            return
        invite_code = (await state.get_data()).get("invite_code")
        if not isinstance(invite_code, str):
            await state.clear()
            await message.answer(texts.INVALID_INVITE)
            return
        try:
            registration = await people.register_invited_user(
                message.from_user.id, message.text, invite_code
            )
        except AlreadyRegisteredError:
            await state.clear()
            await message.answer(texts.ALREADY_REGISTERED)
            return
        except InviteUnavailableError:
            await state.clear()
            await message.answer(texts.INVALID_INVITE)
            return
        except ValueError:
            await message.answer(texts.ASK_NAME_WITH_SPACE)
            return

        await state.clear()
        welcome = (
            texts.WELCOME_MANAGER
            if registration.user.role == UserRole.MANAGER
            else texts.WELCOME_EMPLOYEE
        )
        await message.answer(f"{welcome}\n{texts.menu(registration.user.role)}")
        await _notify_inviter(bot, registration)

    return router


async def _notify_inviter(bot: Bot, registration: InvitedRegistration) -> None:
    """Notify the invitation creator without failing an otherwise valid registration."""
    try:
        await bot.send_message(
            chat_id=registration.inviter.telegram_id,
            text=texts.INVITER_NOTIFICATION.format(
                full_name=f"{registration.user.first_name} {registration.user.last_name}",
                role=texts.role_name(registration.user.role),
            ),
        )
    except TelegramAPIError:
        logger.warning(
            "could not notify invitation creator",
            extra={"telegram_user_id": registration.inviter.telegram_id},
        )
