from httpx import ASGITransport, AsyncClient

from payback import __version__
from payback.api import create_app
from payback.config import Settings


async def test_health_returns_ok(env: dict[str, str]) -> None:
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_health_survives_lifespan_startup_shutdown(env: dict[str, str]) -> None:
    """Entering/leaving the ASGI lifespan must not break /health."""
    app = create_app(Settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/health")
        second = await client.get("/health")

    assert first.status_code == 200
    assert second.status_code == 200
