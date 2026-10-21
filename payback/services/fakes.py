"""In-memory Planfix and notifier doubles for service tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from payback.db.models import Expense, User
from payback.planfix.exceptions import PlanfixError
from payback.planfix.models import PlanfixDirectory, PlanfixDirectoryEntry, PlanfixUser

_FailOn = str | None


@dataclass
class FakePlanfix:
    """Record Planfix mutations and optionally fail on a named step."""

    users: list[PlanfixUser] = field(default_factory=list)
    directory_entries: dict[int, list[PlanfixDirectoryEntry]] = field(default_factory=dict)
    fail_on: _FailOn = None
    create_calls: int = 0
    upload_calls: int = 0
    attach_calls: int = 0
    update_calls: int = 0
    comment_calls: int = 0
    tasks_by_expense: dict[int, int] = field(default_factory=dict)
    files: dict[int, bytes] = field(default_factory=dict)
    attachments: list[tuple[int, int]] = field(default_factory=list)
    task_updates: list[tuple[int, dict[str, object]]] = field(default_factory=list)
    comments: list[tuple[int, str]] = field(default_factory=list)
    _next_task_id: int = 100
    _next_file_id: int = 1000
    _next_comment_id: int = 7000

    async def create_task(
        self,
        expense_id: int,
        *,
        name: str,
        description: str | None,
        manager_planfix_user_id: int | None,
        custom_field_data: list[dict[str, object]],
    ) -> int:
        self.create_calls += 1
        if self.fail_on == "create_task":
            raise PlanfixError("fake create_task failure")
        existing = self.tasks_by_expense.get(expense_id)
        if existing is not None:
            return existing
        task_id = self._next_task_id
        self._next_task_id += 1
        self.tasks_by_expense[expense_id] = task_id
        return task_id

    async def upload_file(self, content: bytes, *, filename: str, content_type: str) -> int:
        del filename, content_type
        self.upload_calls += 1
        if self.fail_on == "upload_file":
            raise PlanfixError("fake upload_file failure")
        file_id = self._next_file_id
        self._next_file_id += 1
        self.files[file_id] = content
        return file_id

    async def attach_file(self, file_id: int, task_id: int) -> None:
        self.attach_calls += 1
        if self.fail_on == "attach_file":
            raise PlanfixError("fake attach_file failure")
        self.attachments.append((file_id, task_id))

    async def list_users(self) -> list[PlanfixUser]:
        return list(self.users)

    async def get_directory(self, directory_id: int) -> PlanfixDirectory:
        return PlanfixDirectory(id=directory_id, name=f"Directory {directory_id}", title_field_id=1)

    async def list_directory_entries(
        self, directory_id: int, title_field_id: int
    ) -> list[PlanfixDirectoryEntry]:
        del title_field_id
        return list(self.directory_entries.get(directory_id, []))

    async def update_task(self, task_id: int, payload: Mapping[str, object]) -> None:
        self.update_calls += 1
        if self.fail_on == "update_task":
            raise PlanfixError("fake update_task failure")
        self.task_updates.append((task_id, dict(payload)))

    async def add_comment(self, task_id: int, description: str) -> int:
        self.comment_calls += 1
        if self.fail_on == "add_comment":
            raise PlanfixError("fake add_comment failure")
        comment_id = self._next_comment_id
        self._next_comment_id += 1
        self.comments.append((task_id, description))
        return comment_id


@dataclass
class FakeNotifier:
    """Record manager notifications without talking to Telegram."""

    messages: list[dict[str, object]] = field(default_factory=list)
    employee_messages: list[dict[str, object]] = field(default_factory=list)
    cleared_keyboards: list[tuple[int, int]] = field(default_factory=list)
    _next_message_id: int = 5000

    async def notify_manager_new_expense(
        self,
        *,
        manager: User,
        employee: User,
        expense: Expense,
        image_bytes: bytes | None,
    ) -> int:
        message_id = self._next_message_id
        self._next_message_id += 1
        self.messages.append(
            {
                "message_id": message_id,
                "manager_id": manager.id,
                "employee_id": employee.id,
                "expense_id": expense.id,
                "has_image": image_bytes is not None,
            }
        )
        return message_id

    async def clear_manager_decision_keyboard(self, *, manager: User, message_id: int) -> None:
        self.cleared_keyboards.append((manager.id, message_id))

    async def notify_employee_decision(
        self,
        *,
        employee: User,
        expense: Expense,
        detail: str | None = None,
    ) -> None:
        self.employee_messages.append(
            {
                "employee_id": employee.id,
                "expense_id": expense.id,
                "status": expense.status,
                "detail": detail,
            }
        )


__all__ = ["FakeNotifier", "FakePlanfix"]
