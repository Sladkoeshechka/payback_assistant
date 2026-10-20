"""Narrow ports used by submission (and later approval) services."""

from collections.abc import Mapping
from typing import Protocol

from payback.db.models import Expense, User
from payback.planfix.models import PlanfixDirectory, PlanfixDirectoryEntry, PlanfixUser


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

    async def get_directory(self, directory_id: int) -> PlanfixDirectory: ...

    async def list_directory_entries(
        self, directory_id: int, title_field_id: int
    ) -> list[PlanfixDirectoryEntry]: ...

    async def update_task(self, task_id: int, payload: Mapping[str, object]) -> None: ...

    async def add_comment(self, task_id: int, description: str) -> int: ...


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

    async def clear_manager_decision_keyboard(
        self, *, manager: User, message_id: int
    ) -> None:
        """Remove approve/reject/question buttons from the manager card."""
        ...

    async def notify_employee_decision(
        self,
        *,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        """Tell the employee the manager's decision (and optional reason/question)."""
        ...


__all__ = ["NotifierPort", "PlanfixPort"]
