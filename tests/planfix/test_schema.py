from typing import Any

import httpx
import pytest
import respx

from payback.config import Settings
from payback.planfix.client import PlanfixClient
from payback.planfix.exceptions import PlanfixSchemaError
from payback.planfix.schema import validate_planfix_schema
from tests.conftest import load_fixture


@respx.mock
async def test_schema_validation_returns_configured_directories(env: dict[str, str]) -> None:
    respx.get("https://example.planfix.ru/rest/customfield/task").mock(
        return_value=httpx.Response(200, json=load_fixture("customfields"))
    )
    respx.get("https://example.planfix.ru/rest/object/17/statuses").mock(
        return_value=httpx.Response(200, json=load_fixture("object_statuses"))
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
    respx.get("https://example.planfix.ru/rest/object/17/statuses").mock(
        return_value=httpx.Response(200, json=load_fixture("object_statuses"))
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


@respx.mock
async def test_schema_validation_rejects_status_name_mismatch(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLANFIX_STATUS_APPROVED", "105")
    monkeypatch.setenv("PLANFIX_STATUS_TO_PAY", "103")
    respx.get("https://example.planfix.ru/rest/customfield/task").mock(
        return_value=httpx.Response(200, json=load_fixture("customfields"))
    )
    respx.get("https://example.planfix.ru/rest/object/17/statuses").mock(
        return_value=httpx.Response(200, json=load_fixture("object_statuses"))
    )
    settings = Settings()
    client = PlanfixClient(settings.planfix)

    with pytest.raises(PlanfixSchemaError, match="PLANFIX_STATUS_APPROVED"):
        await validate_planfix_schema(client, settings.planfix)
    await client.aclose()


@respx.mock
async def test_schema_validation_rejects_ambiguous_status_names(env: dict[str, str]) -> None:
    payload = load_fixture("object_statuses")
    assert isinstance(payload, dict)
    statuses = payload.get("statuses")
    assert isinstance(statuses, list)
    duplicate = {
        "id": 999,
        "name": "Одобрено",
        "isActive": True,
        "texts": [{"lang": "Ru", "name": "Одобрено"}],
    }
    statuses_with_duplicate = [*statuses, duplicate]

    respx.get("https://example.planfix.ru/rest/customfield/task").mock(
        return_value=httpx.Response(200, json=load_fixture("customfields"))
    )
    respx.get("https://example.planfix.ru/rest/object/17/statuses").mock(
        return_value=httpx.Response(
            200,
            json={"result": "success", "statuses": statuses_with_duplicate},
        )
    )
    settings = Settings()
    client = PlanfixClient(settings.planfix)

    with pytest.raises(PlanfixSchemaError, match="ambiguous"):
        await validate_planfix_schema(client, settings.planfix)
    await client.aclose()
