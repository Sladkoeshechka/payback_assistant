"""User-visible bot text for registration, staff, and menu commands."""

# ruff: noqa: RUF001

from datetime import UTC, datetime
from decimal import Decimal
from html import escape

from payback.db.models import Expense, ExpenseStatus, Invite, User, UserRole
from payback.services.draft import SubmissionDraft
from payback.services.notifications import (
    NOTIFY_EMPLOYEE_APPROVED,
    NOTIFY_EMPLOYEE_CLARIFICATION,
    NOTIFY_EMPLOYEE_NEEDS_REVISION,
    NOTIFY_EMPLOYEE_REJECTED,
)
from payback.services.people import StaffOverview

ASK_NAME = "Введите имя и фамилию."
ASK_NAME_WITH_SPACE = "Введите имя и фамилию через пробел."
INVALID_INVITE = "Эта ссылка недействительна, уже использована или истекла."
ALREADY_REGISTERED = "Вы уже зарегистрированы."
INACTIVE_USER = "Ваш доступ отключён. Обратитесь к руководителю."
UNKNOWN_START = "Вы не владелец, приглашение сотрудников только по ссылке!"
WELCOME_EMPLOYEE = "Добро пожаловать! Вы зарегистрированы как сотрудник."
WELCOME_MANAGER = "Добро пожаловать! Вы зарегистрированы как руководитель."
INVITER_NOTIFICATION = "{full_name} подключился как {role}."
MANAGER_ONLY = "Эта команда доступна только руководителям."
EMPLOYEE_ONLY = "Эта команда доступна только сотрудникам."
STAFF_ACTION_UNAVAILABLE = "Действие больше недоступно. Откройте /staff ещё раз."
PLANFIX_LINK_CONFLICT = "Этот пользователь ПланФикса уже связан с другим аккаунтом."
PLANFIX_UNAVAILABLE = "ПланФикс сейчас недоступен. Попробуйте позже."
PLANFIX_USERS_EMPTY = "В аккаунте ПланФикса нет пользователей для связи."
PLANFIX_LINKED = "ПланФикс связан: пользователь #{planfix_user_id}."
REFRESH_DONE = "Кэш справочников сброшен."
REFRESH_UNAVAILABLE = "Кэш справочников ещё не подключён."
NO_EXPENSES = "За последние 30 дней заявок нет."
NO_PENDING = "Нет заявок, ожидающих вашего решения."
INVITE_REVOKED = "Приглашение отозвано."
EMPLOYEE_DEACTIVATED = "Сотрудник {full_name} отключён."
EMPLOYEE_REACTIVATED = "Сотрудник {full_name} снова включён."
CHOOSE_PLANFIX_USER = "Выберите своего пользователя в ПланФиксе:"
INVITE_PROMPT = "Кого вы хотите пригласить?"
INVITE_CREATED = "Приглашение создано: {link}\nОно действует 72 часа и используется один раз."
OWNER_REGISTERED = "Готово!"
GENERIC_ERROR = "Произошла ошибка. Попробуйте ещё раз позже."
RECOGNIZING_RECEIPT = "Распознаю чек…"
RECEIPT_RECOGNIZED = "Чек на {amount} от {purchased_at:%d.%m.%Y %H:%M}."
QR_NOT_FOUND = "Не удалось распознать QR-код на чеке."
QR_AMBIGUOUS = (
    "На фото несколько фискальных QR-кодов. Пришлите снимок с одним чеком."
)
ASK_AMOUNT = "Введите сумму покупки."
ASK_DATE = "Введите дату покупки в формате ДД.ММ.ГГГГ."
ASK_CATEGORY = "Выберите категорию расхода:"
ASK_DIRECTION = "Выберите направление затрат:"
ASK_COMMENT = "Добавьте комментарий или нажмите «Пропустить»."
ASK_COMMENT_REQUIRED = "Опишите покупку и почему нет кассового чека."
ASK_PROOF_PHOTO = "Можно приложить подтверждение (скриншот перевода или поездки)."
INVALID_AMOUNT = "Не удалось разобрать сумму. Введите число, например 1250,50."
INVALID_DATE = "Не удалось разобрать дату. Используйте формат ДД.ММ.ГГГГ."
CATEGORIES_UNAVAILABLE = "Категории не настроены, обратитесь к руководителю"
SUBMISSION_CANCELLED = "Заявка отменена."
SUBMISSION_NOTHING_TO_CANCEL = "Нечего отменять: заявка уже отправлена или не начата."
REPLACE_DRAFT_PROMPT = "Начать новую заявку и отменить текущую?"
NO_RECEIPT_DISABLED = "Подача без чека отключена."
NO_MANAGER = "Нельзя подать заявку: у вас не указан руководитель. Обратитесь к администратору."
SUBMITTED = "Заявка №{task_id} отправлена на согласование."
SUBMITTED_PENDING_PLANFIX = "Заявка принята, отправим её, как только ПланФикс станет доступен."
EDIT_PICK = "Что исправить?"
EDIT_QR_LOCKED = "Сумму и дату, распознанные по QR, изменить нельзя."
APPROVAL_COMING_SOON = "Согласование будет доступно в следующей версии."
ASK_REJECT_REASON = "Укажите причину отказа."
ASK_CLARIFICATION_QUESTION = "Напишите вопрос сотруднику."
DECISION_DONE = "Решение сохранено."
DECISION_ALREADY_TAKEN = "Заявка уже обработана."
DECISION_FORBIDDEN = "Нельзя решить чужую заявку."
DECISION_NOT_FOUND = "Заявка не найдена."
DECISION_IN_PLANFIX = "Решение принято в ПланФиксе."
CLARIFICATION_REPLY_SENT = "Ответ отправлен руководителю."
CLARIFICATION_PLANFIX_UNAVAILABLE = "Не удалось отправить ответ: ПланФикс недоступен."
REVISION_REPLY_SENT = "Ответ по доработке отправлен."
REVISION_PLANFIX_UNAVAILABLE = "Не удалось отправить доработку: ПланФикс недоступен."
NO_RECEIPT_BUTTON = "Трата без чека"
MANAGER_NEW_EXPENSE = (
    "Новая заявка от {employee}\n"
    "Сумма: {amount}\n"
    "Дата: {purchase_date:%d.%m.%Y}\n"
    "Категория: {category}\n"
    "Направление: {direction}\n"
    "Комментарий: {comment}"
)
MANAGER_CLARIFICATION_REPLY = "Ответ сотрудника:\n{reply}"
MANAGER_NO_RECEIPT_MARK = "⚠️ Без кассового чека"

_STATUS_LABELS = {
    ExpenseStatus.PENDING_SUBMISSION: "Ожидает отправки",
    ExpenseStatus.PENDING: "На согласовании",
    ExpenseStatus.CLARIFICATION: "Уточнение",
    ExpenseStatus.APPROVED: "Одобрено",
    ExpenseStatus.REJECTED: "Отклонено",
    ExpenseStatus.NEEDS_REVISION: "Требует доработки",
    ExpenseStatus.TO_PAY: "К выплате",
    ExpenseStatus.REIMBURSED: "Компенсировано",
}


def menu(role: str, *, allow_no_receipt: bool = True) -> str:
    """Return the commands currently available to a newly registered role."""
    if role == UserRole.MANAGER:
        return "Меню руководителя: /invite, /staff, /pending, /refresh, /help"
    if allow_no_receipt:
        return "Меню сотрудника: /my, /noreceipt, /help"
    return "Меню сотрудника: /my, /help"


def role_name(role: str) -> str:
    return "руководитель" if role == UserRole.MANAGER else "сотрудник"


def help_text(
    role: UserRole | None,
    *,
    allow_no_receipt: bool = True,
) -> str:
    """Return role-aware command help."""
    if role == UserRole.MANAGER:
        lines = [
            "Справка руководителя:",
            "/invite — создать приглашение",
            "/staff — сотрудники, приглашения, связь с ПланФиксом",
            "/pending — заявки, ждущие решения",
            "/refresh — сбросить кэш справочников",
            "/help — эта справка",
        ]
    elif role == UserRole.EMPLOYEE:
        lines = [
            "Справка сотрудника:",
            "/my — мои заявки за 30 дней",
        ]
        if allow_no_receipt:
            lines.append("/noreceipt — трата без кассового чека")
        lines.extend(
            [
                "/help — эта справка",
                "Чтобы подать заявку, отправьте фото чека.",
            ]
        )
    else:
        return "Сначала зарегистрируйтесь через /start или по приглашению."
    return "\n".join(lines)


def full_name(user: User) -> str:
    return f"{user.first_name} {user.last_name}"


def format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    formatted = f"{quantized:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} ₽"


def status_label(status: ExpenseStatus) -> str:
    return _STATUS_LABELS[status]


def staff_overview(overview: StaffOverview) -> str:
    """Render the /staff summary without inline-button labels."""
    lines = ["Управление командой"]
    if overview.subordinates:
        lines.append("")
        lines.append("Сотрудники:")
        for employee in overview.subordinates:
            marker = "" if employee.is_active else " (отключён)"
            lines.append(f"• {full_name(employee)}{marker}")
    else:
        lines.append("")
        lines.append("Сотрудников пока нет.")

    if overview.invites:
        lines.append("")
        lines.append("Активные приглашения:")
        for invite in overview.invites:
            lines.append(f"• {_invite_line(invite)}")
    else:
        lines.append("")
        lines.append("Активных приглашений нет.")

    lines.append("")
    if overview.manager.planfix_user_id is None:
        lines.append("ПланФикс: не связан.")
    else:
        lines.append(f"ПланФикс: пользователь #{overview.manager.planfix_user_id}.")
    return "\n".join(lines)


def my_expenses(expenses: list[Expense]) -> str:
    lines = ["Мои заявки за 30 дней:"]
    for expense in expenses:
        if expense.planfix_task_id:
            task = f"№{expense.planfix_task_id}"
        else:
            task = f"черновик #{expense.id}"
        amount = format_amount(expense.amount)
        status = status_label(expense.status)
        lines.append(f"• {task}: {amount}, {expense.purchase_date:%d.%m.%Y}, {status}")
    return "\n".join(lines)


def pending_expenses(expenses: list[Expense]) -> str:
    lines = ["Ждут вашего решения:"]
    for expense in expenses:
        employee = expense.employee
        task = f"№{expense.planfix_task_id}" if expense.planfix_task_id else f"#{expense.id}"
        lines.append(
            f"• {task}: {full_name(employee)} — {format_amount(expense.amount)}, "
            f"{expense.purchase_date:%d.%m.%Y}, {expense.category_name}"
        )
    return "\n".join(lines)


def confirmation_card(draft: SubmissionDraft) -> str:
    """Render the pre-submit expense summary."""
    amount = format_amount(draft.amount) if draft.amount is not None else "—"
    purchase = draft.purchase_date.strftime("%d.%m.%Y") if draft.purchase_date else "—"
    category = draft.category_name or "—"
    direction = draft.direction_name or "—"
    comment = draft.comment or "—"
    if draft.no_receipt:
        receipt = "без кассового чека"
    elif draft.qr_locked:
        receipt = "распознан"
    elif draft.has_image:
        receipt = "приложен"
    else:
        receipt = "нет"
    return (
        "Заявка на расход\n"
        f"Сумма:        {amount}\n"
        f"Дата:         {purchase}\n"
        f"Категория:    {category}\n"
        f"Направление:  {direction}\n"
        f"Комментарий:  {comment}\n"
        f"Чек:          {receipt}"
    )


def manager_expense_card(
    *,
    employee: User,
    expense: Expense,
    reply_text: str | None = None,
) -> str:
    """Caption / body for the manager notification."""
    direction = expense.direction_name or "—"
    comment = expense.comment or "—"
    text = MANAGER_NEW_EXPENSE.format(
        employee=escape(full_name(employee)),
        amount=format_amount(expense.amount),
        purchase_date=expense.purchase_date,
        category=escape(expense.category_name),
        direction=escape(direction),
        comment=escape(comment),
    )
    if expense.no_receipt:
        text = f"{text}\n{MANAGER_NO_RECEIPT_MARK}"
    if reply_text:
        text = f"{text}\n\n{MANAGER_CLARIFICATION_REPLY.format(reply=escape(reply_text))}"
    return text


def _invite_line(invite: Invite) -> str:
    expires = _as_utc(invite.expires_at)
    return f"{role_name(invite.role)}, до {expires:%d.%m.%Y %H:%M} UTC"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "ALREADY_REGISTERED",
    "APPROVAL_COMING_SOON",
    "ASK_AMOUNT",
    "ASK_CATEGORY",
    "ASK_CLARIFICATION_QUESTION",
    "ASK_COMMENT",
    "ASK_COMMENT_REQUIRED",
    "ASK_DATE",
    "ASK_DIRECTION",
    "ASK_NAME",
    "ASK_NAME_WITH_SPACE",
    "ASK_PROOF_PHOTO",
    "ASK_REJECT_REASON",
    "CATEGORIES_UNAVAILABLE",
    "CHOOSE_PLANFIX_USER",
    "CLARIFICATION_PLANFIX_UNAVAILABLE",
    "CLARIFICATION_REPLY_SENT",
    "DECISION_ALREADY_TAKEN",
    "DECISION_DONE",
    "DECISION_FORBIDDEN",
    "DECISION_IN_PLANFIX",
    "DECISION_NOT_FOUND",
    "EDIT_PICK",
    "EDIT_QR_LOCKED",
    "EMPLOYEE_DEACTIVATED",
    "EMPLOYEE_ONLY",
    "EMPLOYEE_REACTIVATED",
    "GENERIC_ERROR",
    "INACTIVE_USER",
    "INVALID_AMOUNT",
    "INVALID_DATE",
    "INVALID_INVITE",
    "INVITER_NOTIFICATION",
    "INVITE_CREATED",
    "INVITE_PROMPT",
    "INVITE_REVOKED",
    "MANAGER_CLARIFICATION_REPLY",
    "MANAGER_NEW_EXPENSE",
    "MANAGER_NO_RECEIPT_MARK",
    "MANAGER_ONLY",
    "NOTIFY_EMPLOYEE_APPROVED",
    "NOTIFY_EMPLOYEE_CLARIFICATION",
    "NOTIFY_EMPLOYEE_NEEDS_REVISION",
    "NOTIFY_EMPLOYEE_REJECTED",
    "NO_EXPENSES",
    "NO_MANAGER",
    "NO_PENDING",
    "NO_RECEIPT_BUTTON",
    "NO_RECEIPT_DISABLED",
    "OWNER_REGISTERED",
    "PLANFIX_LINKED",
    "PLANFIX_LINK_CONFLICT",
    "PLANFIX_UNAVAILABLE",
    "PLANFIX_USERS_EMPTY",
    "QR_AMBIGUOUS",
    "QR_NOT_FOUND",
    "RECEIPT_RECOGNIZED",
    "RECOGNIZING_RECEIPT",
    "REFRESH_DONE",
    "REFRESH_UNAVAILABLE",
    "REPLACE_DRAFT_PROMPT",
    "REVISION_PLANFIX_UNAVAILABLE",
    "REVISION_REPLY_SENT",
    "STAFF_ACTION_UNAVAILABLE",
    "SUBMISSION_CANCELLED",
    "SUBMISSION_NOTHING_TO_CANCEL",
    "SUBMITTED",
    "SUBMITTED_PENDING_PLANFIX",
    "UNKNOWN_START",
    "WELCOME_EMPLOYEE",
    "WELCOME_MANAGER",
    "confirmation_card",
    "format_amount",
    "full_name",
    "help_text",
    "manager_expense_card",
    "menu",
    "my_expenses",
    "pending_expenses",
    "role_name",
    "staff_overview",
    "status_label",
]
