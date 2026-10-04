from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from payback.planfix.fields import (
    custom_fields,
    date_value,
    directory_value,
    number,
    read_custom_fields,
    read_date_value,
    read_directory_value,
)


def test_outbound_field_values_use_planfix_shapes() -> None:
    assert number(Decimal("12.50")) == 12.5
    assert number(7) == 7
    assert date_value(date(2026, 10, 2)) == {"date": "02-10-2026"}
    assert read_date_value({"date": "02-10-2026"}) == date(2026, 10, 2)
    assert directory_value(8) == {"id": 8}
    assert read_directory_value({"id": 8, "value": "Топливо"}) == 8


@pytest.mark.parametrize("value", [{}, {"id": False}, {"id": "8"}])
def test_read_directory_value_rejects_invalid_ids(value: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="numeric id"):
        read_directory_value(value)


def test_custom_fields_omits_unset_values() -> None:
    assert custom_fields({10: "text", 11: None, 12: False}) == [
        {"field": {"id": 10}, "value": "text"},
        {"field": {"id": 12}, "value": False},
    ]


def test_read_custom_fields_extracts_typed_values() -> None:
    fields: list[dict[str, Any]] = [
        {"field": {"id": 10}, "value": {"date": "02-10-2026"}},
        {"field": {"id": 11}, "value": {"id": 8, "value": "Топливо"}},
        {"field": {"id": "not-an-id"}, "value": "ignored"},
    ]

    assert read_custom_fields(fields) == {
        10: {"date": "02-10-2026"},
        11: {"id": 8, "value": "Топливо"},
    }
