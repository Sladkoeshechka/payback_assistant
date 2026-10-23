"""Async client for the small, verified Planfix REST API surface."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from payback.config import PlanfixSettings
from payback.planfix.exceptions import PlanfixError, PlanfixNotFound, PlanfixScopeDenied
from payback.planfix.models import (
    PlanfixComment,
    PlanfixDirectory,
    PlanfixDirectoryEntry,
    PlanfixUser,
)

_DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
_MAX_ATTEMPTS = 3
_PAGE_SIZE = 100
Sleep = Callable[[float], Awaitable[None]]


class PlanfixClient:
    """Make authenticated requests and normalize Planfix's response envelopes.

    The deterministic key is deliberately limited to task creation. Other mutation
    endpoints do not have a stable local identifier that can safely be reused.
    """

    def __init__(
        self,
        settings: PlanfixSettings,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._base_url = settings.rest_base_url
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {settings.api_token.get_secret_value()}",
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=_DEFAULT_TIMEOUT,
        )
        self._object_id = settings.object_id

    async def __aenter__(self) -> "PlanfixClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def task_idempotency_key(expense_id: int) -> str:
        """Return a stable key for every attempted creation of one local expense."""
        return str(uuid5(NAMESPACE_URL, f"payback-expense:{expense_id}"))

    async def create_task(
        self,
        expense_id: int,
        *,
        name: str,
        description: str | None,
        manager_planfix_user_id: int | None,
        custom_field_data: list[dict[str, object]],
    ) -> int:
        payload: dict[str, object] = {
            "name": name,
            "object": {"id": self._object_id},
            "customFieldData": custom_field_data,
        }
        if manager_planfix_user_id is not None:
            payload["assignees"] = {"users": [{"id": f"user:{manager_planfix_user_id}"}]}
        if description:
            payload["description"] = description
        response = await self._request(
            "POST",
            "/task/",
            json=payload,
            headers={"Idempotency-Key": self.task_idempotency_key(expense_id)},
        )
        return _required_int(response, "id", "task creation")

    async def get_task(self, task_id: int, field_ids: Iterable[int] = ()) -> dict[str, Any]:
        fields = ["id", "name", "status", "object", "assigner", "assignees", "participants"]
        fields.extend(str(field_id) for field_id in field_ids)
        response = await self._request(
            "GET", f"/task/{task_id}", params={"fields": ",".join(fields)}
        )
        task = response.get("task")
        if not isinstance(task, dict):
            raise PlanfixError("Planfix returned no task for a successful task lookup")
        return task

    async def update_task(self, task_id: int, payload: Mapping[str, object]) -> None:
        await self._request("POST", f"/task/{task_id}", json=dict(payload))

    async def upload_file(self, content: bytes, *, filename: str, content_type: str) -> int:
        response = await self._request(
            "POST",
            "/file/",
            files={"file": (filename, content, content_type)},
        )
        return _required_int(response, "id", "file upload")

    async def attach_file(self, file_id: int, task_id: int) -> None:
        await self._request("POST", f"/file/{file_id}/attach/task", params={"id": task_id})

    async def add_comment(self, task_id: int, description: str) -> int:
        response = await self._request(
            "POST", f"/task/{task_id}/comments/", json={"description": description}
        )
        return _required_int(response, "id", "comment creation")

    async def list_comments(
        self, task_id: int, *, offset: int = 0, page_size: int = _PAGE_SIZE
    ) -> list[PlanfixComment]:
        response = await self._request(
            "POST",
            f"/task/{task_id}/comments/list",
            json={
                "offset": offset,
                "pageSize": page_size,
                "fields": "id,description,owner,dateTime,type",
            },
        )
        comments = response.get("comments", [])
        if not isinstance(comments, list):
            raise PlanfixError("Planfix returned malformed comments")
        return [_comment(item) for item in comments if _is_human_comment(item)]

    async def list_users(self) -> list[PlanfixUser]:
        response = await self._request(
            "POST",
            "/user/list",
            json={"offset": 0, "pageSize": _PAGE_SIZE, "fields": "id,name,lastname"},
        )
        users = response.get("users", [])
        if not isinstance(users, list):
            raise PlanfixError("Planfix returned malformed users")
        return [_user(item) for item in users]

    async def get_task_custom_fields(self) -> list[dict[str, Any]]:
        response = await self._request(
            "GET", "/customfield/task", params={"fields": "id,name,type,directoryId"}
        )
        fields = response.get("customfields", [])
        if not isinstance(fields, list):
            raise PlanfixError("Planfix returned malformed task fields")
        return [field for field in fields if isinstance(field, dict)]

    async def get_directory(self, directory_id: int) -> PlanfixDirectory:
        response = await self._request(
            "GET", f"/directory/{directory_id}", params={"fields": "id,name,fields"}
        )
        directory = response.get("directory")
        if not isinstance(directory, dict):
            raise PlanfixError("Planfix returned no directory for a successful directory lookup")
        fields = directory.get("fields")
        if not isinstance(fields, list) or not fields or not isinstance(fields[0], dict):
            raise PlanfixError(f"Directory {directory_id} has no title field")
        return PlanfixDirectory(
            id=_required_int(directory, "id", "directory"),
            name=_required_string(directory, "name", "directory"),
            title_field_id=_required_int(fields[0], "id", "directory title field"),
        )

    async def list_directory_entries(
        self, directory_id: int, title_field_id: int
    ) -> list[PlanfixDirectoryEntry]:
        response = await self._request(
            "POST",
            f"/directory/{directory_id}/entry/list",
            json={"offset": 0, "pageSize": _PAGE_SIZE, "fields": f"key,{title_field_id}"},
        )
        entries = response.get("directoryEntries", [])
        if not isinstance(entries, list):
            raise PlanfixError("Planfix returned malformed directory entries")
        return [_directory_entry(item, title_field_id) for item in entries]

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        request_headers = {**self._headers, **kwargs.pop("headers", {})}
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = await self._client.request(
                    method, f"{self._base_url}{url}", headers=request_headers, **kwargs
                )
            except httpx.TransportError as error:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise PlanfixError("Planfix transport failed after retries") from error
                await self._sleep(0.25 * (2**attempt))
                continue

            if response.status_code >= 500:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise PlanfixError(
                        f"Planfix returned HTTP {response.status_code} after retries"
                    )
                await self._sleep(0.25 * (2**attempt))
                continue

            return _parse_response(response)

        raise AssertionError("unreachable")


def _parse_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as error:
        raise PlanfixError(
            f"Planfix returned invalid JSON (HTTP {response.status_code})"
        ) from error
    if not isinstance(payload, dict):
        raise PlanfixError("Planfix returned a JSON value instead of an object")
    if payload.get("result") == "success":
        return payload

    code = payload.get("code")
    api_error = payload.get("error")
    message = api_error if isinstance(api_error, str) else "Planfix rejected the request"
    if code == 1000:
        raise PlanfixNotFound(message)
    if code == 5 or "scope denied" in message.lower():
        raise PlanfixScopeDenied(message)
    raise PlanfixError(message)


def _required_int(value: Mapping[str, Any], key: str, subject: str) -> int:
    result = value.get(key)
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    raise PlanfixError(f"Planfix returned no numeric {key} for {subject}")


def _required_string(value: Mapping[str, Any], key: str, subject: str) -> str:
    result = value.get(key)
    if isinstance(result, str):
        return result
    raise PlanfixError(f"Planfix returned no {key} for {subject}")


def _is_human_comment(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("type") == "Comment"
        and bool(value.get("description"))
    )


def _comment(value: object) -> PlanfixComment:
    if not isinstance(value, dict):
        raise PlanfixError("Planfix returned a malformed comment")
    owner = value.get("owner")
    owner_id = owner.get("id") if isinstance(owner, dict) else None
    return PlanfixComment(
        id=_required_int(value, "id", "comment"),
        description=_required_string(value, "description", "comment"),
        owner_id=owner_id if isinstance(owner_id, str) else None,
    )


def _user(value: object) -> PlanfixUser:
    if not isinstance(value, dict):
        raise PlanfixError("Planfix returned a malformed user")
    return PlanfixUser(
        id=_required_int(value, "id", "user"),
        name=_required_string(value, "name", "user"),
        last_name=_required_string(value, "lastname", "user"),
    )


def _directory_entry(value: object, title_field_id: int) -> PlanfixDirectoryEntry:
    if not isinstance(value, dict):
        raise PlanfixError("Planfix returned a malformed directory entry")
    fields = value.get("customFieldData")
    if not isinstance(fields, list):
        raise PlanfixError("Directory entry has no title data; check its title field configuration")
    for field_data in fields:
        if not isinstance(field_data, dict):
            continue
        field = field_data.get("field")
        title = field_data.get("value")
        if isinstance(field, dict) and field.get("id") == title_field_id and isinstance(title, str):
            return PlanfixDirectoryEntry(
                key=_required_int(value, "key", "directory entry"), name=title
            )
    raise PlanfixError("Directory entry has no title data; check its title field configuration")


__all__ = ["PlanfixClient"]
