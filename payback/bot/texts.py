"""User-visible bot text for registration and invitations."""

ASK_NAME = "Введите имя и фамилию."
ASK_NAME_WITH_SPACE = "Введите имя и фамилию через пробел."
INVALID_INVITE = "Эта ссылка недействительна, уже использована или истекла."
ALREADY_REGISTERED = "Вы уже зарегистрированы."
INACTIVE_USER = "Ваш доступ отключён. Обратитесь к руководителю."
UNKNOWN_START = "Вы не владелец, приглашение сотрудников только по ссылке!"
WELCOME_EMPLOYEE = "Добро пожаловать! Вы зарегистрированы как сотрудник."
WELCOME_MANAGER = "Добро пожаловать! Вы зарегистрированы как руководитель."
INVITER_NOTIFICATION = "{full_name} подключился как {role}."


def menu(role: str) -> str:
    """Return the commands currently available to a newly registered role."""
    if role == "manager":
        return "Меню руководителя: /invite, /staff, /pending, /refresh, /help"
    return "Меню сотрудника: /my, /help"


def role_name(role: str) -> str:
    return "руководитель" if role == "manager" else "сотрудник"


__all__ = [
    "ALREADY_REGISTERED",
    "ASK_NAME",
    "ASK_NAME_WITH_SPACE",
    "INACTIVE_USER",
    "INVALID_INVITE",
    "INVITER_NOTIFICATION",
    "UNKNOWN_START",
    "WELCOME_EMPLOYEE",
    "WELCOME_MANAGER",
    "menu",
    "role_name",
]
