import json

import httpx
import pytest
import respx
from conftest import load_fixture

from payback.config import Settings
from payback.planfix.client import PlanfixClient
from payback.planfix.exceptions import PlanfixError, PlanfixNotFound, PlanfixScopeDenied


@pytest.fixture
def planfix_settings(env: dict[str, str]) -> Settings:
    return Settings()


@respx.mock
async def test_create_task_uses_card_shape_and_stable_idempotency_key(
    planfix_settings: Settings,
) -> None:
    route = respx.post("https://example.planfix.ru/rest/task/").mock(
        return_value=httpx.Response(200, json=load_fixture("task_create"))
    )
    client = PlanfixClient(planfix_settings.planfix)

    task_id = await client.create_task(
        42,
        name="Expense",
        description="Taxi",
        manager_planfix_user_id=3,
        custom_field_data=[{"field": {"id": 141074}, "value": 500.0}],
    )

    assert task_id == 36
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-planfix-token"
    assert request.headers["Idempotency-Key"] == PlanfixClient.task_idempotency_key(42)
    assert PlanfixClient.task_idempotency_key(42) == PlanfixClient.task_idempotency_key(42)
    assert PlanfixClient.task_idempotency_key(42) != PlanfixClient.task_idempotency_key(43)
    assert json.loads(request.content) == {
        "name": "Expense",
        "description": "Taxi",
        "object": {"id": 17},
        "assignees": {"users": [{"id": "user:3"}]},
        "customFieldData": [{"field": {"id": 141074}, "value": 500.0}],
    }
    await client.aclose()


@respx.mock
async def test_task_operations_and_202_are_successful(planfix_settings: Settings) -> None:
    task = respx.get("https://example.planfix.ru/rest/task/36").mock(
        return_value=httpx.Response(200, json=load_fixture("task_get_pending"))
    )
    update = respx.post("https://example.planfix.ru/rest/task/36").mock(
        return_value=httpx.Response(202, json={"result": "success"})
    )
    client = PlanfixClient(planfix_settings.planfix)

    loaded = await client.get_task(36, [141074, 141370])
    await client.update_task(36, {"status": {"id": 103}})

    assert loaded["status"]["id"] == 101
    assert task.calls[0].request.url.params["fields"].endswith("141074,141370")
    assert json.loads(update.calls[0].request.content) == {"status": {"id": 103}}
    await client.aclose()


@respx.mock
async def test_file_comments_and_users_normalize_captured_responses(
    planfix_settings: Settings,
) -> None:
    upload = respx.post("https://example.planfix.ru/rest/file/").mock(
        return_value=httpx.Response(200, json=load_fixture("file_upload"))
    )
    respx.post("https://example.planfix.ru/rest/file/1115336/attach/task").mock(
        return_value=httpx.Response(200, json=load_fixture("file_attach"))
    )
    respx.post("https://example.planfix.ru/rest/task/36/comments/").mock(
        return_value=httpx.Response(200, json=load_fixture("comment_add"))
    )
    respx.post("https://example.planfix.ru/rest/task/36/comments/list").mock(
        return_value=httpx.Response(200, json=load_fixture("comments_list"))
    )
    respx.post("https://example.planfix.ru/rest/user/list").mock(
        return_value=httpx.Response(200, json=load_fixture("user_list"))
    )
    client = PlanfixClient(planfix_settings.planfix)

    file_id = await client.upload_file(b"jpeg", filename="receipt.jpg", content_type="image/jpeg")
    await client.attach_file(file_id, 36)
    comment_id = await client.add_comment(36, "Reason")
    comments = await client.list_comments(36)
    users = await client.list_users()

    assert file_id == 1115336
    assert b'name="file"' in upload.calls[0].request.content
    assert comment_id > 0
    assert all(comment.description for comment in comments)
    assert all(comment.owner_id for comment in comments)
    assert users[0].id > 0
    await client.aclose()


@respx.mock
async def test_retries_5xx_three_total_attempts(planfix_settings: Settings) -> None:
    route = respx.get("https://example.planfix.ru/rest/task/36").mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(503),
            httpx.Response(200, json={"result": "success", "task": {"id": 36}}),
        ]
    )
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    client = PlanfixClient(planfix_settings.planfix, sleep=sleep)
    assert (await client.get_task(36))["id"] == 36
    assert route.call_count == 3
    assert delays == [0.25, 0.5]
    await client.aclose()


@respx.mock
async def test_logical_failures_have_specific_errors(planfix_settings: Settings) -> None:
    route = respx.get("https://example.planfix.ru/rest/task/404")
    client = PlanfixClient(planfix_settings.planfix)

    route.mock(return_value=httpx.Response(200, json=load_fixture("error_task_not_found")))
    with pytest.raises(PlanfixNotFound):
        await client.get_task(404)

    route.mock(
        return_value=httpx.Response(
            200,
            json={"result": "fail", "code": 5, "error": "Scope denied, method not allowed"},
        )
    )
    with pytest.raises(PlanfixScopeDenied):
        await client.get_task(404)

    route.mock(return_value=httpx.Response(200, json=load_fixture("error_unknown_token")))
    with pytest.raises(PlanfixError):
        await client.get_task(404)
    assert route.call_count == 3
    await client.aclose()


@respx.mock
async def test_transport_failure_retries_then_raises(planfix_settings: Settings) -> None:
    route = respx.get("https://example.planfix.ru/rest/task/36").mock(
        side_effect=httpx.ConnectError("offline")
    )
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    client = PlanfixClient(planfix_settings.planfix, sleep=sleep)
    with pytest.raises(PlanfixError, match="transport failed"):
        await client.get_task(36)
    assert route.call_count == 3
    assert delays == [0.25, 0.5]
    await client.aclose()
