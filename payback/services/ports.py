"""Narrow ports used by domain services.

``NotifierPort`` lives in ``payback.services.notifications`` and is re-exported here
so existing ``from payback.services.ports import NotifierPort`` imports keep working.
"""

from collections.abc import Mapping
from typing import Protocol

from payback.planfix.models import PlanfixDirectory, PlanfixDirectoryEntry, PlanfixUser
from payback.services.notifications import NotifierPort


class PlanfixPort(Protocol):
    """Planfix operations required to push and update expense tasks."""

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


__all__ = ["NotifierPort", "PlanfixPort"]
