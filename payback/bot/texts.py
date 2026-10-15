"""User-visible bot text for registration, staff, and menu commands."""

# ruff: noqa: RUF001

from datetime import UTC, datetime
from decimal import Decimal

from payback.db.models import Expense, ExpenseStatus, Invite, User, UserRole
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
CHOOSE_PLANFIX_USER = "Выберите своего пользователя в ПланФиксе:"
INVITE_PROMPT = "Кого вы хотите пригласить?"
INVITE_CREATED = "Приглашение создано: {link}\nОно действует 72 часа и используется один раз."
OWNER_REGISTERED = "Готово!"
GENERIC_ERROR = "Произошла ошибка. Попробуйте ещё раз позже."
DEV_AS_USAGE = "Использование: /as employee или /as manager"
DEV_AS_NEED_REGISTER = "Сначала зарегистрируйтесь через /start."
DEV_AS_SWITCHED = "Роль переключена: {role}.\n{menu}"

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


def menu(role: str) -> str:
    """Return the commands currently available to a newly registered role."""
    if role == UserRole.MANAGER:
        return "Меню руководителя: /invite, /staff, /pending, /refresh, /help"
    return "Меню сотрудника: /my, /help"


def role_name(role: str) -> str:
    return "руководитель" if role == UserRole.MANAGER else "сотрудник"


def help_text(role: UserRole | None, *, dev_mode: bool = False) -> str:
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
            "/help — эта справка",
            "Чтобы подать заявку, отправьте фото чека (после подключения подачи).",
        ]
    else:
        return "Сначала зарегистрируйтесь через /start или по приглашению."
    if dev_mode:
        lines.append("/as employee|manager — сменить роль (только DEV_MODE)")
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
            lines.append(f"• {full_name(employee)}")
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


def _invite_line(invite: Invite) -> str:
    expires = _as_utc(invite.expires_at)
    return f"{role_name(invite.role)}, до {expires:%d.%m.%Y %H:%M} UTC"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "ALREADY_REGISTERED",
    "ASK_NAME",
    "ASK_NAME_WITH_SPACE",
    "CHOOSE_PLANFIX_USER",
    "DEV_AS_NEED_REGISTER",
    "DEV_AS_SWITCHED",
    "DEV_AS_USAGE",
    "EMPLOYEE_DEACTIVATED",
    "EMPLOYEE_ONLY",
    "GENERIC_ERROR",
    "INACTIVE_USER",
    "INVALID_INVITE",
    "INVITER_NOTIFICATION",
    "INVITE_CREATED",
    "INVITE_PROMPT",
    "INVITE_REVOKED",
    "MANAGER_ONLY",
    "NO_EXPENSES",
    "NO_PENDING",
    "OWNER_REGISTERED",
    "PLANFIX_LINKED",
    "PLANFIX_LINK_CONFLICT",
    "PLANFIX_UNAVAILABLE",
    "PLANFIX_USERS_EMPTY",
    "REFRESH_DONE",
    "REFRESH_UNAVAILABLE",
    "STAFF_ACTION_UNAVAILABLE",
    "UNKNOWN_START",
    "WELCOME_EMPLOYEE",
    "WELCOME_MANAGER",
    "format_amount",
    "full_name",
    "help_text",
    "menu",
    "my_expenses",
    "pending_expenses",
    "role_name",
    "staff_overview",
    "status_label",
]
