"""Telegram handlers for manager approve / reject / clarification."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from payback.bot import texts
from payback.bot.states import ManagerDecision
from payback.config import Settings
from payback.db.models import User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.services.approval import (
    ApprovalForbiddenError,
    ApprovalService,
    ExpenseNotFoundError,
    ExpenseNotPendingError,
)
from payback.services.ports import NotifierPort, PlanfixPort

_EXPENSE_ID_KEY = "decision_expense_id"


def create_router() -> Router:
    router = Router()

    @router.callback_query(F.data.startswith("mgr:approve:"))
    async def approve(
        callback: CallbackQuery,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        expense_id = _parse_expense_id(callback.data)
        if expense_id is None or not _is_manager(user):
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        assert user is not None
        if planfix is None or notifier is None:
            await callback.answer(texts.PLANFIX_UNAVAILABLE, show_alert=True)
            return
        service = _service(expenses_repo, planfix, notifier, settings)
        try:
            await service.approve(expense_id=expense_id, manager=user)
        except ExpenseNotFoundError:
            await callback.answer(texts.DECISION_NOT_FOUND, show_alert=True)
            return
        except ApprovalForbiddenError:
            await callback.answer(texts.DECISION_FORBIDDEN, show_alert=True)
            return
        except ExpenseNotPendingError:
            await callback.answer(texts.DECISION_ALREADY_TAKEN, show_alert=True)
            return
        await callback.answer(texts.DECISION_DONE)

    @router.callback_query(F.data.startswith("mgr:reject:"))
    async def start_reject(callback: CallbackQuery, state: FSMContext, user: User | None) -> None:
        expense_id = _parse_expense_id(callback.data)
        if expense_id is None or not _is_manager(user):
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        await state.set_state(ManagerDecision.waiting_reject_reason)
        await state.update_data({_EXPENSE_ID_KEY: expense_id})
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(texts.ASK_REJECT_REASON)

    @router.callback_query(F.data.startswith("mgr:ask:"))
    async def start_ask(callback: CallbackQuery, state: FSMContext, user: User | None) -> None:
        expense_id = _parse_expense_id(callback.data)
        if expense_id is None or not _is_manager(user):
            await callback.answer(texts.MANAGER_ONLY, show_alert=True)
            return
        await state.set_state(ManagerDecision.waiting_question)
        await state.update_data({_EXPENSE_ID_KEY: expense_id})
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(texts.ASK_CLARIFICATION_QUESTION)

    @router.message(ManagerDecision.waiting_reject_reason)
    async def complete_reject(
        message: Message,
        state: FSMContext,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        if message.text is None or not _is_manager(user):
            return
        assert user is not None
        reason = message.text.strip()
        if not reason:
            await message.answer(texts.ASK_REJECT_REASON)
            return
        expense_id = await _expense_id_from_state(state)
        if expense_id is None:
            await state.clear()
            return
        if planfix is None or notifier is None:
            await message.answer(texts.PLANFIX_UNAVAILABLE)
            return
        service = _service(expenses_repo, planfix, notifier, settings)
        try:
            await service.reject(expense_id=expense_id, manager=user, reason=reason)
        except ExpenseNotFoundError:
            await message.answer(texts.DECISION_NOT_FOUND)
        except ApprovalForbiddenError:
            await message.answer(texts.DECISION_FORBIDDEN)
        except ExpenseNotPendingError:
            await message.answer(texts.DECISION_ALREADY_TAKEN)
        else:
            await message.answer(texts.DECISION_DONE)
        await state.clear()

    @router.message(ManagerDecision.waiting_question)
    async def complete_ask(
        message: Message,
        state: FSMContext,
        settings: Settings,
        user: User | None,
        expenses_repo: ExpensesRepo,
        planfix: PlanfixPort | None = None,
        notifier: NotifierPort | None = None,
    ) -> None:
        if message.text is None or not _is_manager(user):
            return
        assert user is not None
        question = message.text.strip()
        if not question:
            await message.answer(texts.ASK_CLARIFICATION_QUESTION)
            return
        expense_id = await _expense_id_from_state(state)
        if expense_id is None:
            await state.clear()
            return
        if planfix is None or notifier is None:
            await message.answer(texts.PLANFIX_UNAVAILABLE)
            return
        service = _service(expenses_repo, planfix, notifier, settings)
        try:
            await service.ask(expense_id=expense_id, manager=user, question=question)
        except ExpenseNotFoundError:
            await message.answer(texts.DECISION_NOT_FOUND)
        except ApprovalForbiddenError:
            await message.answer(texts.DECISION_FORBIDDEN)
        except ExpenseNotPendingError:
            await message.answer(texts.DECISION_ALREADY_TAKEN)
        else:
            await message.answer(texts.DECISION_DONE)
        await state.clear()

    return router


def _service(
    expenses_repo: ExpensesRepo,
    planfix: PlanfixPort,
    notifier: NotifierPort,
    settings: Settings,
) -> ApprovalService:
    return ApprovalService(
        expenses_repo,
        planfix,
        notifier,
        settings.planfix.statuses,
    )


def _parse_expense_id(data: str | None) -> int | None:
    if data is None:
        return None
    raw = data.rsplit(":", 1)[-1]
    try:
        return int(raw)
    except ValueError:
        return None


async def _expense_id_from_state(state: FSMContext) -> int | None:
    raw = (await state.get_data()).get(_EXPENSE_ID_KEY)
    return raw if isinstance(raw, int) else None


def _is_manager(user: User | None) -> bool:
    return user is not None and user.role == UserRole.MANAGER and user.is_active


__all__ = ["create_router"]
