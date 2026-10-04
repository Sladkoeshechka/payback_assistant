from typing import Any

import httpx
import pytest
import respx
from conftest import load_fixture

from payback.config import Settings
from payback.planfix.client import PlanfixClient
from payback.planfix.exceptions import PlanfixSchemaError
from payback.planfix.schema import validate_planfix_schema


@respx.mock
async def test_schema_validation_returns_configured_directories(env: dict[str, str]) -> None:
    respx.get("https://example.planfix.ru/rest/customfield/task").mock(
        return_value=httpx.Response(200, json=load_fixture("customfields"))
    )
    settings = Settings()
    client = PlanfixClient(settings.planfix)

    schema = await validate_planfix_schema(client, settings.planfix)

    assert schema.category_directory_id == 11176
    assert schema.direction_directory_id == 11178
    await client.aclose()


@respx.mock
async def test_schema_validation_aggregates_missing_and_invalid_fields(env: dict[str, str]) -> None:
    payload = load_fixture("customfields")
    assert isinstance(payload, dict)
    fields = payload["customfields"]
    assert isinstance(fields, list)
    changed: list[dict[str, Any]] = [dict(field) for field in fields if isinstance(field, dict)]
    changed[:] = [field for field in changed if field["id"] != 141380]
    category = next(field for field in changed if field["id"] == 141370)
    category["type"] = 0
    category.pop("directoryId")

    respx.get("https://example.planfix.ru/rest/customfield/task").mock(
        return_value=httpx.Response(200, json={"result": "success", "customfields": changed})
    )
    settings = Settings()
    client = PlanfixClient(settings.planfix)

    with pytest.raises(PlanfixSchemaError) as error:
        await validate_planfix_schema(client, settings.planfix)

    message = str(error.value)
    assert "141380" in message
    assert "141370" in message
    assert "directoryId" in message
    await client.aclose()
