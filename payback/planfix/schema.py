"""Validation of the configured expense-card fields at application startup."""

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


__all__ = ["validate_planfix_schema"]
