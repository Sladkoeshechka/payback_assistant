import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from payback.bot import texts
from payback.bot.people import menu_for
from payback.bot.states import EmployeeRegistration
from payback.config import Settings
from payback.db.models import User
from payback.db.models.enums import UserRole
from payback.services.people import (
    AlreadyRegisteredError,
    InvitedRegistration,
    InviteUnavailableError,
    PeopleService,
)

logger = logging.getLogger(__name__)


def create_router() -> Router:
    """Create handlers for entering and completing invitation-based registration."""
    router = Router()

    @router.message(CommandStart(deep_link=True))
    async def start_from_invite(
        message: Message,
        state: FSMContext,
        command: CommandObject,
        people: PeopleService,
        user: User | None,
        settings: Settings,
    ) -> None:
        if message.from_user is None or command.args is None:
            await message.answer(texts.INVALID_INVITE)
            return
        if user is not None:
            await state.clear()
            await message.answer(f"{texts.ALREADY_REGISTERED}\n{menu_for(user, settings)}")
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
        settings: Settings,
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
        await message.answer(f"{welcome}\n{menu_for(registration.user, settings)}")
        await _notify_inviter(bot, registration)

    return router


async def _notify_inviter(bot: Bot, registration: InvitedRegistration) -> None:
    """Notify the invitation creator without failing an otherwise valid registration."""
    try:
        await bot.send_message(
            chat_id=registration.inviter.telegram_id,
            text=texts.INVITER_NOTIFICATION.format(
                full_name=texts.full_name(registration.user),
                role=texts.role_name(registration.user.role),
            ),
        )
    except TelegramAPIError:
        logger.warning(
            "could not notify invitation creator",
            extra={"telegram_user_id": registration.inviter.telegram_id},
        )
