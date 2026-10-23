
from httpx import ASGITransport, AsyncClient

from payback.api import create_app
from payback.config import Settings


async def test_webhook_rejects_wrong_secret(env: dict[str, str]) -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/planfix",
            json={"task": 34, "secret": "wrong", "status": "Одобрено"},
        )

    assert response.status_code == 403
    assert app.state.webhook_events == []


async def test_webhook_rejects_missing_secret_field(env: dict[str, str]) -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/planfix",
            json={"task": 34, "status": "Одобрено"},
        )

    assert response.status_code == 422
    assert app.state.webhook_events == []


async def test_webhook_accepts_valid_secret_and_queues_work(env: dict[str, str]) -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/planfix",
            json={
                "task": 34,
                "secret": env["WEBHOOK_SECRET"],
                "status": "Одобрено",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert app.state.webhook_events == [(34, "Одобрено")]
