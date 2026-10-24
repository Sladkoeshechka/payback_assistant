"""Telegram FSM for photo and no-receipt expense submission (stage 7)."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from payback.bot import texts
from payback.bot.keyboards import (
    confirm_keyboard,
    directory_keyboard,
    edit_field_keyboard,
    proof_photo_keyboard,
    qr_missing_keyboard,
    replace_draft_keyboard,
    skip_comment_keyboard,
)
from payback.bot.states import ExpenseSubmission
from payback.config import Settings
from payback.db.models import ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.planfix.directories import DirectoryCache
from payback.planfix.exceptions import PlanfixError
from payback.planfix.models import PlanfixDirectoryEntry, PlanfixSchema
from payback.receipts.fiscal import FiscalParseError, parse_fiscal_qr
from payback.receipts.qr import QRCodeNotFoundError, decode_qr
from payback.receipts.validation import (
    ReceiptValidationError,
    validate_amount,
    validate_image,
    validate_purchase_date,
    validate_receipt,
)
from payback.services.draft import SubmissionDraft
from payback.services.ports import NotifierPort, PlanfixPort
from payback.services.submission import DuplicateReceiptError, SubmissionService

_DRAFT_KEY = "draft"
_PENDING_FILE_ID = "pending_file_id"
_PENDING_CONTENT_TYPE = "pending_content_type"
_PENDING_FILENAME = "pending_filename"
_EDIT_RETURN = "edit_return"
_PREVIOUS_STATE = "previous_state"


def create_router() -> Router:
    router = Router()

    @router.message(Command("cancel"))
    async def cmd_cancel(
        message: Message,
        state: FSMContext,
        settings: Settings,
        user: User | None,
    ) -> None:
        current = await state.get_state()
        await state.clear()
        if current is None:
            return
        menu = texts.menu(
            user.role if user is not None else UserRole.EMPLOYEE,
            allow_no_receipt=settings.allow_no_receipt,
        )
        await message.answer(f"{texts.SUBMISSION_CANCELLED}\n{menu}")

    @router.message(Command("noreceipt"))
    @router.message(F.text == texts.NO_RECEIPT_BUTTON)
    async def start_no_receipt(
        message: Message,
        state: FSMContext,
        settings: Settings,
        user: User | None,
    ) -> None:
        if not _is_employee(user):
            await message.answer(texts.EMPLOYEE_ONLY)
            return
        if not settings.allow_no_receipt:
            await message.answer(texts.NO_RECEIPT_DISABLED)
            return
        await state.clear()
        draft = SubmissionDraft(no_receipt=True)
        await _save_draft(state, draft)
        await message.answer(texts.ASK_AMOUNT)
        await state.set_state(ExpenseSubmission.no_receipt_amount)

    @router.message(F.photo | (F.document & F.document.mime_type.in_({"image/jpeg", "image/png"})))
    async def on_image(
        message: Message,
        state: FSMContext,
        bot: Bot,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        directory_cache: DirectoryCache | None = None,
        planfix_schema: PlanfixSchema | None = None,
    ) -> None:
        if not _is_employee(user):
            return
        current = await state.get_state()
        if current == ExpenseSubmission.no_receipt_proof.state:
            await _handle_proof_photo(message, state, bot)
            return
        if current is not None and current.startswith(ExpenseSubmission.__name__):
            file_id, content_type, filename = _image_meta(message)
            await state.update_data(
                {
                    _PENDING_FILE_ID: file_id,
                    _PENDING_CONTENT_TYPE: content_type,
                    _PENDING_FILENAME: filename,
                    _PREVIOUS_STATE: current,
                }
            )
            await message.answer(
                texts.REPLACE_DRAFT_PROMPT,
                reply_markup=replace_draft_keyboard(),
            )
            await state.set_state(ExpenseSubmission.replace_confirm)
            return
        await _begin_photo_submission(
            message,
            state,
            bot,
            settings,
            expenses_repo,
            directory_cache,
            planfix_schema,
        )

    @router.callback_query(F.data == "sub:replace:yes", ExpenseSubmission.replace_confirm)
    async def replace_yes(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        settings: Settings,
        expenses_repo: ExpensesRepo,
        directory_cache: DirectoryCache | None = None,
        planfix_schema: PlanfixSchema | None = None,
    ) -> None:
        if not isinstance(callback.message, Message):
            return
        data = await state.get_data()
        file_id = data.get(_PENDING_FILE_ID)
        content_type = data.get(_PENDING_CONTENT_TYPE) or "image/jpeg"
        filename = data.get(_PENDING_FILENAME) or "receipt.jpg"
        await state.clear()
        await callback.answer()
        if not isinstance(file_id, str):
            return
        await _process_receipt_image(
            callback.message,
            state,
            bot,
            settings,
            expenses_repo,
            directory_cache,
            planfix_schema,
            file_id=file_id,
            content_type=content_type,
            filename=filename,
        )

    @router.callback_query(F.data == "sub:replace:no", ExpenseSubmission.replace_confirm)
    async def replace_no(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        previous = data.get(_PREVIOUS_STATE)
        if isinstance(previous, str):
            await state.set_state(previous)
        else:
            await state.set_state(ExpenseSubmission.confirm)
        await callback.answer("Продолжаем текущую заявку.")

    @router.callback_query(F.data == "sub:retry")
    async def retry_photo(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer("Пришлите новое фото чека.")

    @router.callback_query(F.data == "sub:manual")
    async def start_manual(callback: CallbackQuery, state: FSMContext) -> None:
        draft = await _load_draft(state)
        draft.fn = None
        draft.fd = None
        draft.fp = None
        draft.qr_locked = False
        await _save_draft(state, draft)
        await state.set_state(ExpenseSubmission.manual_amount)
        # await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(texts.ASK_AMOUNT)

    @router.message(ExpenseSubmission.manual_amount)
    @router.message(ExpenseSubmission.edit_amount)
    @router.message(ExpenseSubmission.no_receipt_amount)
    async def on_amount(message: Message, state: FSMContext, settings: Settings) -> None:
        if message.text is None:
            return
        amount = _parse_amount(message.text)
        if amount is None:
            await message.answer(texts.INVALID_AMOUNT)
            return
        current = await state.get_state()
        no_receipt = current == ExpenseSubmission.no_receipt_amount.state
        try:
            validate_amount(amount, settings, no_receipt=no_receipt)
        except ReceiptValidationError as error:
            await message.answer(str(error))
            return
        draft = await _load_draft(state)
        draft.amount = amount
        await _save_draft(state, draft)
        if current == ExpenseSubmission.edit_amount.state:
            await _show_confirmation(message, state)
            return
        await message.answer(texts.ASK_DATE)
        if no_receipt:
            await state.set_state(ExpenseSubmission.no_receipt_date)
        else:
            await state.set_state(ExpenseSubmission.manual_date)

    @router.message(ExpenseSubmission.manual_date)
    @router.message(ExpenseSubmission.edit_date)
    @router.message(ExpenseSubmission.no_receipt_date)
    async def on_date(
        message: Message,
        state: FSMContext,
        settings: Settings,
        directory_cache: DirectoryCache | None = None,
        planfix_schema: PlanfixSchema | None = None,
    ) -> None:
        if message.text is None:
            return
        purchase_date = _parse_date(message.text)
        if purchase_date is None:
            await message.answer(texts.INVALID_DATE)
            return
        try:
            validate_purchase_date(purchase_date, settings)
        except ReceiptValidationError as error:
            await message.answer(str(error))
            return
        draft = await _load_draft(state)
        draft.purchase_date = purchase_date
        await _save_draft(state, draft)
        current = await state.get_state()
        if current == ExpenseSubmission.edit_date.state:
            await _show_confirmation(message, state)
            return
        await _ask_category(message, state, directory_cache, planfix_schema)

    @router.callback_query(F.data.startswith("sub:cat:"))
    async def on_category(
        callback: CallbackQuery,
        state: FSMContext,
        directory_cache: DirectoryCache | None = None,
        planfix_schema: PlanfixSchema | None = None,
    ) -> None:
        if callback.data is None or not isinstance(callback.message, Message):
            return
        raw_id = callback.data.rsplit(":", 1)[1]
        try:
            category_id = int(raw_id)
        except ValueError:
            await callback.answer()
            return
        entries = await _category_entries(directory_cache, planfix_schema)
        chosen = next((entry for entry in entries if entry.key == category_id), None)
        if chosen is None:
            await callback.answer(texts.CATEGORIES_UNAVAILABLE, show_alert=True)
            return
        draft = await _load_draft(state)
        draft.category_id = chosen.key
        draft.category_name = chosen.name
        await _save_draft(state, draft)
        await callback.answer()
        data = await state.get_data()
        if data.get(_EDIT_RETURN):
            await state.update_data({_EDIT_RETURN: False})
            await _show_confirmation(callback.message, state)
            return
        await _ask_direction(callback.message, state, directory_cache, planfix_schema)

    @router.callback_query(F.data.startswith("sub:dir:"))
    async def on_direction(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.data is None or not isinstance(callback.message, Message):
            return
        raw = callback.data.rsplit(":", 1)[1]
        draft = await _load_draft(state)
        if raw == "none":
            draft.direction_id = None
            draft.direction_name = None
        else:
            try:
                direction_id = int(raw)
            except ValueError:
                await callback.answer()
                return
            draft.direction_id = direction_id
            data = await state.get_data()
            names = data.get("direction_names") or {}
            draft.direction_name = names.get(str(direction_id)) or names.get(direction_id)
        await _save_draft(state, draft)
        await callback.answer()
        data = await state.get_data()
        if data.get(_EDIT_RETURN):
            await state.update_data({_EDIT_RETURN: False})
            await _show_confirmation(callback.message, state)
            return
        await _ask_comment(callback.message, state)

    @router.callback_query(F.data == "sub:skip_comment")
    async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
        if not isinstance(callback.message, Message):
            return
        draft = await _load_draft(state)
        if draft.no_receipt:
            await callback.answer(texts.ASK_COMMENT_REQUIRED, show_alert=True)
            return
        draft.comment = None
        await _save_draft(state, draft)
        await callback.answer()
        data = await state.get_data()
        if data.get(_EDIT_RETURN):
            await state.update_data({_EDIT_RETURN: False})
            await _show_confirmation(callback.message, state)
            return
        await _show_confirmation(callback.message, state)

    @router.message(ExpenseSubmission.comment)
    @router.message(ExpenseSubmission.edit_comment)
    @router.message(ExpenseSubmission.no_receipt_comment)
    async def on_comment(message: Message, state: FSMContext) -> None:
        if message.text is None:
            return
        comment = message.text.strip()
        if not comment:
            draft = await _load_draft(state)
            if draft.no_receipt:
                await message.answer(texts.ASK_COMMENT_REQUIRED)
                return
            comment_value = None
        else:
            comment_value = comment
        draft = await _load_draft(state)
        draft.comment = comment_value
        await _save_draft(state, draft)
        current = await state.get_state()
        if current == ExpenseSubmission.edit_comment.state:
            await _show_confirmation(message, state)
            return
        if draft.no_receipt:
            await message.answer(texts.ASK_PROOF_PHOTO, reply_markup=proof_photo_keyboard())
            await state.set_state(ExpenseSubmission.no_receipt_proof)
            return
        await _show_confirmation(message, state)

    @router.callback_query(F.data == "sub:proof:skip", ExpenseSubmission.no_receipt_proof)
    async def skip_proof(callback: CallbackQuery, state: FSMContext) -> None:
        if not isinstance(callback.message, Message):
            return
        await callback.answer()
        await _show_confirmation(callback.message, state)

    @router.callback_query(F.data == "sub:proof:wait", ExpenseSubmission.no_receipt_proof)
    async def wait_proof(callback: CallbackQuery) -> None:
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer("Пришлите фото подтверждения.")

    @router.callback_query(F.data == "sub:send", ExpenseSubmission.confirm)
    async def send_expense(
        callback: CallbackQuery,
        state: FSMContext,
        settings: Settings,
        user: User | None,
        users_repo: UsersRepo,
        expenses_repo: ExpensesRepo,
        bot: Bot,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        if not isinstance(callback.message, Message) or not _is_employee(user):
            return
        assert user is not None
        if planfix is None or notifier is None:
            await callback.answer(texts.PLANFIX_UNAVAILABLE, show_alert=True)
            return
        manager = await _resolve_manager(users_repo, user)
        if manager is None:
            await callback.answer(texts.NO_MANAGER, show_alert=True)
            return
        draft = await _load_draft(state)
        if draft.has_image and draft.image_bytes is None and draft.telegram_file_id:
            draft.image_bytes = await _download_file(bot, draft.telegram_file_id)
        service = SubmissionService(
            expenses_repo,
            planfix,
            notifier,
            settings.planfix.fields,
        )
        try:
            expense = await service.submit(draft, employee=user, manager=manager)
        except DuplicateReceiptError as error:
            await state.clear()
            await callback.answer()
            await _clear_inline_keyboard(callback.message)
            await callback.message.answer(str(error))
            return
        await state.clear()
        await callback.answer()
        await _clear_inline_keyboard(callback.message)
        if expense.status is ExpenseStatus.PENDING and expense.planfix_task_id is not None:
            await callback.message.answer(texts.SUBMITTED.format(task_id=expense.planfix_task_id))
        else:
            await callback.message.answer(texts.SUBMITTED_PENDING_PLANFIX)

    @router.callback_query(F.data == "sub:edit", ExpenseSubmission.confirm)
    async def edit_expense(callback: CallbackQuery, state: FSMContext) -> None:
        if not isinstance(callback.message, Message):
            return
        draft = await _load_draft(state)
        await state.set_state(ExpenseSubmission.edit_pick)
        await callback.answer()
        notice = f"\n{texts.EDIT_QR_LOCKED}" if draft.qr_locked else ""
        await callback.message.answer(
            f"{texts.EDIT_PICK}{notice}",
            reply_markup=edit_field_keyboard(qr_locked=draft.qr_locked),
        )

    @router.callback_query(F.data == "sub:edit:back", ExpenseSubmission.edit_pick)
    async def edit_back(callback: CallbackQuery, state: FSMContext) -> None:
        if not isinstance(callback.message, Message):
            return
        await callback.answer()
        await _show_confirmation(callback.message, state)

    @router.callback_query(F.data.startswith("sub:edit:"), ExpenseSubmission.edit_pick)
    async def edit_field(
        callback: CallbackQuery,
        state: FSMContext,
        directory_cache: DirectoryCache | None = None,
        planfix_schema: PlanfixSchema | None = None,
    ) -> None:
        if callback.data is None or not isinstance(callback.message, Message):
            return
        field = callback.data.rsplit(":", 1)[1]
        draft = await _load_draft(state)
        await callback.answer()
        if field == "amount":
            if draft.qr_locked:
                await callback.message.answer(texts.EDIT_QR_LOCKED)
                return
            await state.set_state(ExpenseSubmission.edit_amount)
            await callback.message.answer(texts.ASK_AMOUNT)
            return
        if field == "date":
            if draft.qr_locked:
                await callback.message.answer(texts.EDIT_QR_LOCKED)
                return
            await state.set_state(ExpenseSubmission.edit_date)
            await callback.message.answer(texts.ASK_DATE)
            return
        if field == "category":
            await state.update_data({_EDIT_RETURN: True})
            await _ask_category(callback.message, state, directory_cache, planfix_schema)
            return
        if field == "direction":
            await state.update_data({_EDIT_RETURN: True})
            await _ask_direction(callback.message, state, directory_cache, planfix_schema)
            return
        if field == "comment":
            await state.set_state(ExpenseSubmission.edit_comment)
            prompt = texts.ASK_COMMENT_REQUIRED if draft.no_receipt else texts.ASK_COMMENT
            markup = None if draft.no_receipt else skip_comment_keyboard()
            await callback.message.answer(prompt, reply_markup=markup)

    @router.callback_query(F.data == "sub:cancel")
    async def cancel_submission(
        callback: CallbackQuery,
        state: FSMContext,
        settings: Settings,
        user: User | None,
    ) -> None:
        await state.clear()
        await callback.answer()
        if isinstance(callback.message, Message):
            await _clear_inline_keyboard(callback.message)
            menu = texts.menu(
                user.role if user is not None else UserRole.EMPLOYEE,
                allow_no_receipt=settings.allow_no_receipt,
            )
            await callback.message.answer(f"{texts.SUBMISSION_CANCELLED}\n{menu}")

    return router


async def _clear_inline_keyboard(message: Message) -> None:
    """Remove Отправить / Исправить / Отменить from the confirmation card."""
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        return


async def _begin_photo_submission(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    expenses_repo: ExpensesRepo,
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
) -> None:
    file_id, content_type, filename = _image_meta(message)
    await _process_receipt_image(
        message,
        state,
        bot,
        settings,
        expenses_repo,
        directory_cache,
        planfix_schema,
        file_id=file_id,
        content_type=content_type,
        filename=filename,
    )


async def _process_receipt_image(
    message: Message,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    expenses_repo: ExpensesRepo,
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
    *,
    file_id: str,
    content_type: str,
    filename: str,
) -> None:
    await message.answer(texts.RECOGNIZING_RECEIPT)
    image_bytes = await _download_file(bot, file_id)
    try:
        validate_image(image_bytes, content_type)
    except ReceiptValidationError as error:
        await message.answer(str(error))
        return

    draft = SubmissionDraft(
        telegram_file_id=file_id,
        image_filename=filename,
        image_content_type=content_type,
    )
    try:
        qr_value = await decode_qr(image_bytes)
        receipt = parse_fiscal_qr(qr_value)
        validate_receipt(receipt, settings)
    except (QRCodeNotFoundError, FiscalParseError, ReceiptValidationError):
        await _save_draft(state, draft)
        await state.set_state(ExpenseSubmission.awaiting_qr_choice)
        await message.answer(texts.QR_NOT_FOUND, reply_markup=qr_missing_keyboard())
        return

    draft.amount = receipt.amount
    draft.purchase_date = receipt.purchased_at.date()
    draft.fn = receipt.fn
    draft.fd = receipt.fd
    draft.fp = receipt.fp
    draft.qr_locked = True
    await _save_draft(state, draft)

    existing = await expenses_repo.get_by_fiscal_data(receipt.fn, receipt.fd, receipt.fp)
    if existing is not None:
        await state.clear()
        await message.answer(str(DuplicateReceiptError(existing)))
        return

    await message.answer(
        texts.RECEIPT_RECOGNIZED.format(
            amount=texts.format_amount(receipt.amount),
            purchased_at=receipt.purchased_at,
        )
    )
    await _ask_category(message, state, directory_cache, planfix_schema)


async def _handle_proof_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    file_id, content_type, filename = _image_meta(message)
    image_bytes = await _download_file(bot, file_id)
    try:
        validate_image(image_bytes, content_type)
    except ReceiptValidationError as error:
        await message.answer(str(error))
        return
    draft = await _load_draft(state)
    draft.telegram_file_id = file_id
    draft.image_filename = filename
    draft.image_content_type = content_type
    await _save_draft(state, draft)
    await _show_confirmation(message, state)


def _image_meta(message: Message) -> tuple[str, str, str]:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, "image/jpeg", "receipt.jpg"
    document = message.document
    assert document is not None
    return (
        document.file_id,
        document.mime_type or "image/jpeg",
        document.file_name or "receipt.jpg",
    )


async def _download_file(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    assert file.file_path is not None
    buffer = BytesIO()
    await bot.download_file(file.file_path, destination=buffer)
    return buffer.getvalue()


async def _ask_category(
    message: Message,
    state: FSMContext,
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
) -> None:
    try:
        entries = await _category_entries(directory_cache, planfix_schema)
    except PlanfixError:
        await state.clear()
        await message.answer(texts.CATEGORIES_UNAVAILABLE)
        return
    if not entries:
        await state.clear()
        await message.answer(texts.CATEGORIES_UNAVAILABLE)
        return
    await state.set_state(ExpenseSubmission.category)
    await message.answer(
        texts.ASK_CATEGORY,
        reply_markup=directory_keyboard(entries, prefix="sub:cat"),
    )


async def _ask_direction(
    message: Message,
    state: FSMContext,
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
) -> None:
    try:
        entries = await _direction_entries(directory_cache, planfix_schema)
    except PlanfixError:
        entries = ()
    if not entries:
        await _ask_comment(message, state)
        return
    await state.update_data(
        direction_names={str(entry.key): entry.name for entry in entries},
    )
    await state.set_state(ExpenseSubmission.direction)
    await message.answer(
        texts.ASK_DIRECTION,
        reply_markup=directory_keyboard(entries, prefix="sub:dir", include_none=True),
    )


async def _ask_comment(message: Message, state: FSMContext) -> None:
    draft = await _load_draft(state)
    if draft.no_receipt:
        await state.set_state(ExpenseSubmission.no_receipt_comment)
        await message.answer(texts.ASK_COMMENT_REQUIRED)
        return
    await state.set_state(ExpenseSubmission.comment)
    await message.answer(texts.ASK_COMMENT, reply_markup=skip_comment_keyboard())


async def _show_confirmation(message: Message, state: FSMContext) -> None:
    draft = await _load_draft(state)
    await state.set_state(ExpenseSubmission.confirm)
    await message.answer(texts.confirmation_card(draft), reply_markup=confirm_keyboard())


async def _category_entries(
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
) -> tuple[PlanfixDirectoryEntry, ...]:
    if directory_cache is None or planfix_schema is None:
        return ()
    return await directory_cache.get(planfix_schema.category_directory_id)


async def _direction_entries(
    directory_cache: DirectoryCache | None,
    planfix_schema: PlanfixSchema | None,
) -> tuple[PlanfixDirectoryEntry, ...]:
    if directory_cache is None or planfix_schema is None:
        return ()
    return await directory_cache.get(planfix_schema.direction_directory_id)


async def _resolve_manager(users_repo: UsersRepo, employee: User) -> User | None:
    if employee.manager_id is None:
        return None
    return await users_repo.get_by_id(employee.manager_id)


async def _save_draft(state: FSMContext, draft: SubmissionDraft) -> None:
    await state.update_data({_DRAFT_KEY: draft.to_fsm_data()})


async def _load_draft(state: FSMContext) -> SubmissionDraft:
    data = await state.get_data()
    raw = data.get(_DRAFT_KEY)
    if not isinstance(raw, dict):
        return SubmissionDraft()
    return SubmissionDraft.from_fsm_data(raw)


def _is_employee(user: User | None) -> bool:
    return user is not None and user.role == UserRole.EMPLOYEE and user.is_active


def _parse_amount(text: str) -> Decimal | None:
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not amount.is_finite():
        return None
    return amount


def _parse_date(text: str) -> date | None:
    cleaned = text.strip()
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


__all__ = ["create_router"]
