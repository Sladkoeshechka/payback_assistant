from unittest.mock import AsyncMock, MagicMock

import pytest

from payback.config import Settings
from payback.main import connect_planfix, offline_planfix_stack
from payback.planfix.exceptions import PlanfixSchemaError
from payback.planfix.models import PlanfixSchema
from payback.services.fakes import FakePlanfix


def test_offline_planfix_stack_has_sample_directories() -> None:
    planfix, schema = offline_planfix_stack()
    assert isinstance(planfix, FakePlanfix)
    assert schema.category_directory_id in planfix.directory_entries
    assert schema.direction_directory_id in planfix.directory_entries
    assert planfix.directory_entries[schema.category_directory_id]


@pytest.mark.asyncio
async def test_connect_planfix_falls_back_only_with_dev_mode(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """FakePlanfix fallback requires DEV_MODE (and ALLOW_DEV_MODE)."""
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_MODE", "true")
    settings = Settings()

    client = MagicMock()
    client.aclose = AsyncMock()
    monkeypatch.setattr("payback.main.PlanfixClient", lambda _cfg: client)
    monkeypatch.setattr(
        "payback.main.validate_planfix_schema",
        AsyncMock(side_effect=RuntimeError("network down")),
    )

    planfix, schema, live = await connect_planfix(settings)

    assert isinstance(planfix, FakePlanfix)
    assert isinstance(schema, PlanfixSchema)
    assert live is None
    client.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_connect_planfix_without_dev_mode_reraises_transport_error(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings()
    client = MagicMock()
    client.aclose = AsyncMock()
    monkeypatch.setattr("payback.main.PlanfixClient", lambda _cfg: client)
    monkeypatch.setattr(
        "payback.main.validate_planfix_schema",
        AsyncMock(side_effect=RuntimeError("network down")),
    )

    with pytest.raises(RuntimeError, match="network down"):
        await connect_planfix(settings)
    client.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_connect_planfix_schema_error_never_falls_back(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_MODE", "true")
    settings = Settings()
    client = MagicMock()
    client.aclose = AsyncMock()
    monkeypatch.setattr("payback.main.PlanfixClient", lambda _cfg: client)
    monkeypatch.setattr(
        "payback.main.validate_planfix_schema",
        AsyncMock(side_effect=PlanfixSchemaError("bad status map")),
    )

    with pytest.raises(PlanfixSchemaError, match="bad status map"):
        await connect_planfix(settings)
    client.aclose.assert_awaited()
