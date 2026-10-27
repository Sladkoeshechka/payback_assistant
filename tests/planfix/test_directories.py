import httpx
import pytest
import respx
from tests.conftest import load_fixture

from payback.config import Settings
from payback.planfix.client import PlanfixClient
from payback.planfix.directories import DirectoryCache
from payback.planfix.exceptions import PlanfixError


@respx.mock
async def test_directory_cache_uses_metadata_title_field_and_ttl(env: dict[str, str]) -> None:
    metadata = respx.get("https://example.planfix.ru/rest/directory/11176").mock(
        return_value=httpx.Response(200, json=load_fixture("directory_categories"))
    )
    entries = respx.post("https://example.planfix.ru/rest/directory/11176/entry/list").mock(
        return_value=httpx.Response(200, json=load_fixture("directory_categories_entries"))
    )
    now = 100.0
    settings = Settings()
    client = PlanfixClient(settings.planfix)
    cache = DirectoryCache(client, clock=lambda: now)

    first = await cache.get(11176)
    second = await cache.get(11176)

    assert first == second
    assert first[0].name == "Материалы"
    assert metadata.call_count == 1
    assert entries.call_count == 1
    assert entries.calls[0].request.content == b'{"offset":0,"pageSize":100,"fields":"key,34632"}'
    await client.aclose()


@respx.mock
async def test_directory_cache_serves_stale_success_after_refresh_failure(
    env: dict[str, str],
) -> None:
    metadata = respx.get("https://example.planfix.ru/rest/directory/11176").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("directory_categories")),
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
        ]
    )
    respx.post("https://example.planfix.ru/rest/directory/11176/entry/list").mock(
        return_value=httpx.Response(200, json=load_fixture("directory_categories_entries"))
    )
    clock = [0.0]
    settings = Settings()
    client = PlanfixClient(settings.planfix, sleep=_no_sleep)
    cache = DirectoryCache(client, clock=lambda: clock[0])

    fresh = await cache.get(11176)
    clock[0] = 601.0
    stale = await cache.get(11176)

    assert stale == fresh
    assert metadata.call_count == 4
    await client.aclose()


@respx.mock
async def test_directory_cache_accepts_empty_but_rejects_missing_title_data(
    env: dict[str, str],
) -> None:
    metadata = respx.get("https://example.planfix.ru/rest/directory/11176").mock(
        return_value=httpx.Response(200, json=load_fixture("directory_categories"))
    )
    entries = respx.post("https://example.planfix.ru/rest/directory/11176/entry/list")
    settings = Settings()
    client = PlanfixClient(settings.planfix)
    cache = DirectoryCache(client)

    entries.mock(
        return_value=httpx.Response(200, json={"result": "success", "directoryEntries": []})
    )
    assert await cache.get(11176) == ()

    cache.invalidate()
    entries.mock(
        return_value=httpx.Response(
            200, json={"result": "success", "directoryEntries": [{"key": 7}]}
        )
    )
    with pytest.raises(PlanfixError, match="title data"):
        await cache.get(11176)
    assert metadata.call_count == 2
    await client.aclose()


async def _no_sleep(_: float) -> None:
    return None
