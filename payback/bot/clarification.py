"""Telegram handlers for employee clarification replies (stage 8B)."""

from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from payback.bot import texts
from payback.config import Settings
from payback.db.models import User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.clarification import ClarificationService, NoClarificationPendingError
from payback.services.ports import NotifierPort, PlanfixPort


def create_router() -> Router:
    router = Router()

    @router.message(F.text, ~F.text.startswith("/"))
    async def on_text_reply(
        message: Message,
        state: FSMContext,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        users_repo: UsersRepo,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        if not await _should_handle_reply(state, user, expenses_repo):
            raise SkipHandler
        assert user is not None
        assert message.text is not None
        service = _service(expenses_repo, planfix, notifier, settings)
        if service is None:
            await message.answer(texts.CLARIFICATION_PLANFIX_UNAVAILABLE)
            return
        manager = await _manager(users_repo, user)
        try:
            await service.reply(employee=user, manager=manager, text=message.text.strip())
        except NoClarificationPendingError:
            raise SkipHandler from None
        await message.answer(texts.CLARIFICATION_REPLY_SENT)

    @router.message(F.photo | (F.document & F.document.mime_type.in_({"image/jpeg", "image/png"})))
    async def on_photo_reply(
        message: Message,
        state: FSMContext,
        bot: Bot,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        users_repo: UsersRepo,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        if not await _should_handle_reply(state, user, expenses_repo):
            raise SkipHandler
        assert user is not None
        service = _service(expenses_repo, planfix, notifier, settings)
        if service is None:
            await message.answer(texts.CLARIFICATION_PLANFIX_UNAVAILABLE)
            return
        file_id, content_type, filename = _image_meta(message)
        image_bytes = await _download_file(bot, file_id)
        caption = message.caption.strip() if message.caption else None
        manager = await _manager(users_repo, user)
        try:
            await service.reply(
                employee=user,
                manager=manager,
                text=caption,
                image_bytes=image_bytes,
                image_filename=filename,
                image_content_type=content_type,
            )
        except NoClarificationPendingError:
            raise SkipHandler from None
        await message.answer(texts.CLARIFICATION_REPLY_SENT)

    return router


async def _should_handle_reply(
    state: FSMContext, user: User | None, expenses_repo: ExpensesRepo
) -> bool:
    if user is None or user.role != UserRole.EMPLOYEE or not user.is_active:
        return False
    if await state.get_state() is not None:
        return False
    expense = await expenses_repo.get_clarification_for_employee(user.id)
    return expense is not None


def _service(
    expenses_repo: ExpensesRepo,
    planfix: PlanfixPort | None,
    notifier: NotifierPort | None,
    settings: Settings,
) -> ClarificationService | None:
    if planfix is None or notifier is None:
        return None
    return ClarificationService(
        expenses_repo,
        planfix,
        notifier,
        settings.planfix.statuses,
    )


async def _manager(users_repo: UsersRepo, employee: User) -> User | None:
    if employee.manager_id is None:
        return None
    return await users_repo.get_by_id(employee.manager_id)


def _image_meta(message: Message) -> tuple[str, str, str]:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, "image/jpeg", "reply.jpg"
    document = message.document
    assert document is not None
    return (
        document.file_id,
        document.mime_type or "image/jpeg",
        document.file_name or "reply.jpg",
    )


async def _download_file(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    assert file.file_path is not None
    buffer = BytesIO()
    await bot.download_file(file.file_path, destination=buffer)
    return buffer.getvalue()


__all__ = ["create_router"]
