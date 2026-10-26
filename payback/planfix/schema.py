"""Validation of configured expense-card fields and statuses at startup."""

# ruff: noqa: RUF001

from collections.abc import Mapping
from typing import Any

from payback.config import PlanfixSettings
from payback.planfix.client import PlanfixClient
from payback.planfix.exceptions import PlanfixSchemaError
from payback.planfix.models import PlanfixSchema

_SHORT_TEXT = 0
_NUMBER = 1
_DATE = 3
_CHECKBOX = 7
_DIRECTORY_ENTRY = 9

_STATUS_NAME_ALIASES = {
    "pending": frozenset({"На согласовании"}),
    "clarification": frozenset({"Уточнение"}),
    "approved": frozenset({"Одобрено"}),
    "rejected": frozenset({"Отклонено"}),
    "needs_revision": frozenset({"Требует доработки"}),
    "to_pay": frozenset({"К выплате"}),
    # Known account alias from planfix-notes.md.
    "reimbursed": frozenset({"Компенсировано", "компенсация завершена"}),
}


def _expected_types(settings: PlanfixSettings) -> dict[int, int]:
    fields = settings.fields
    return {
        fields.amount: _NUMBER,
        fields.purchase_date: _DATE,
        fields.category: _DIRECTORY_ENTRY,
        fields.direction: _DIRECTORY_ENTRY,
        fields.employee: _SHORT_TEXT,
        fields.fn: _SHORT_TEXT,
        fields.fd: _SHORT_TEXT,
        fields.fp: _SHORT_TEXT,
        fields.no_receipt: _CHECKBOX,
        fields.payment_date: _DATE,
    }


async def validate_planfix_schema(
    client: PlanfixClient, settings: PlanfixSettings
) -> PlanfixSchema:
    """Check configured IDs and types without trusting duplicate display names."""
    configured = _expected_types(settings)
    found = _by_id(await client.get_task_custom_fields())
    problems: list[str] = []

    for field_id, expected_type in configured.items():
        field = found.get(field_id)
        if field is None:
            problems.append(f"missing configured custom field {field_id}")
        elif field.get("type") != expected_type:
            problems.append(
                f"custom field {field_id} has type {field.get('type')!r}, expected {expected_type}"
            )

    category_directory_id = _directory_id(found.get(settings.fields.category), "category", problems)
    direction_directory_id = _directory_id(
        found.get(settings.fields.direction), "direction", problems
    )
    _validate_statuses(await client.list_object_statuses(), settings, problems)

    if problems:
        raise PlanfixSchemaError("Planfix expense-card schema mismatch: " + "; ".join(problems))
    assert category_directory_id is not None
    assert direction_directory_id is not None
    return PlanfixSchema(
        category_directory_id=category_directory_id,
        direction_directory_id=direction_directory_id,
    )


def _by_id(fields: list[dict[str, Any]]) -> dict[int, Mapping[str, Any]]:
    return {field_id: field for field in fields if isinstance((field_id := field.get("id")), int)}


def _directory_id(field: Mapping[str, Any] | None, label: str, problems: list[str]) -> int | None:
    if field is None:
        return None
    directory_id = field.get("directoryId")
    if isinstance(directory_id, int) and not isinstance(directory_id, bool):
        return directory_id
    problems.append(f"{label} field {field.get('id')!r} has no directoryId")
    return None


def _validate_statuses(
    statuses: list[dict[str, Any]], settings: PlanfixSettings, problems: list[str]
) -> None:
    by_id: dict[int, Mapping[str, Any]] = {
        status_id: status
        for status in statuses
        if isinstance((status_id := status.get("id")), int) and isinstance(status, dict)
    }
    for attr_name, allowed_names in _STATUS_NAME_ALIASES.items():
        configured_id = getattr(settings.statuses, attr_name)
        actual = by_id.get(configured_id)
        env_key = f"PLANFIX_STATUS_{attr_name.upper()}"
        if actual is None:
            problems.append(f"missing configured status id {configured_id} for {env_key}")
            continue
        normalized_actual_names = _normalized_status_names(actual)
        normalized_allowed = {name.casefold() for name in allowed_names}
        if normalized_actual_names.isdisjoint(normalized_allowed):
            problems.append(
                f"{env_key}={configured_id} points to "
                f"{actual.get('name')!r}, expected one of {sorted(allowed_names)!r}"
            )

        matching_ids = [
            status_id
            for status_id, status in by_id.items()
            if not _normalized_status_names(status).isdisjoint(normalized_allowed)
        ]
        if len(matching_ids) > 1:
            problems.append(
                f"{env_key} is ambiguous: names {sorted(allowed_names)!r} match ids "
                f"{sorted(matching_ids)!r}"
            )


def _normalized_status_names(status: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    root_name = status.get("name")
    if isinstance(root_name, str):
        names.add(root_name.strip().casefold())
    texts = status.get("texts")
    if isinstance(texts, list):
        for text in texts:
            if not isinstance(text, dict):
                continue
            translated = text.get("name")
            if isinstance(translated, str):
                names.add(translated.strip().casefold())
    return {name for name in names if name}


__all__ = ["validate_planfix_schema"]
