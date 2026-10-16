"""Narrow ports used by submission (and later approval) services."""

from typing import Protocol

from payback.db.models import Expense, User
from payback.planfix.models import PlanfixUser


class PlanfixPort(Protocol):
    """Planfix operations required to push an expense into a task."""

    async def create_task(
        self,
        expense_id: int,
        *,
        name: str,
        description: str | None,
        manager_planfix_user_id: int | None,
        custom_field_data: list[dict[str, object]],
    ) -> int: ...

    async def upload_file(self, content: bytes, *, filename: str, content_type: str) -> int: ...

    async def attach_file(self, file_id: int, task_id: int) -> None: ...

    async def list_users(self) -> list[PlanfixUser]: ...


class NotifierPort(Protocol):
    """Outbound notifications decoupled from aiogram."""

    async def notify_manager_new_expense(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
        image_bytes: bytes | None,
    ) -> int:
        """Send the manager card and return the Telegram message id."""
        ...


__all__ = ["NotifierPort", "PlanfixPort"]
