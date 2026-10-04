"""Planfix custom-field value conversion.

The REST API uses the same envelope for every custom field, while the value shape is
specific to its type. Keeping that detail here prevents services from hand-writing
slightly different task-card payloads.
"""

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any

FieldValue = str | int | float | bool | dict[str, int] | dict[str, str]


def number(value: Decimal | int | float) -> int | float:
    """Return a JSON number without leaking ``Decimal`` into httpx's encoder."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def date_value(value: date) -> dict[str, str]:
    """Serialize a Planfix date field in its documented day-first format."""
    return {"date": value.strftime("%d-%m-%Y")}


def directory_value(key: int) -> dict[str, int]:
    """Serialize a reference to a directory entry."""
    return {"id": key}


def read_date_value(value: Mapping[str, object]) -> date:
    """Deserialize a Planfix date field."""
    raw_date = value.get("date")
    if not isinstance(raw_date, str):
        raise ValueError("Planfix date value has no date")
    return datetime.strptime(raw_date, "%d-%m-%Y").date()


def read_directory_value(value: Mapping[str, object]) -> int:
    """Deserialize a selected Planfix directory-entry key."""
    key = value.get("id")
    if isinstance(key, int) and not isinstance(key, bool):
        return key
    raise ValueError("Planfix directory value has no numeric id")


def custom_field(field_id: int, value: FieldValue) -> dict[str, object]:
    """Wrap one converted value in Planfix's custom-field envelope."""
    return {"field": {"id": field_id}, "value": value}


def custom_fields(values: Mapping[int, FieldValue | None]) -> list[dict[str, object]]:
    """Serialize present custom fields, omitting values intentionally left unset."""
    return [
        custom_field(field_id, value) for field_id, value in values.items() if value is not None
    ]


def read_custom_fields(items: Iterable[Mapping[str, Any]]) -> dict[int, object]:
    """Extract typed values from a task or directory ``customFieldData`` list."""
    result: dict[int, object] = {}
    for item in items:
        field = item.get("field")
        if not isinstance(field, Mapping):
            continue
        field_id = field.get("id")
        if isinstance(field_id, int) and "value" in item:
            result[field_id] = item["value"]
    return result


__all__ = [
    "FieldValue",
    "custom_field",
    "custom_fields",
    "date_value",
    "directory_value",
    "number",
    "read_custom_fields",
    "read_date_value",
    "read_directory_value",
]
