import asyncio

from httpx import ASGITransport, AsyncClient

from payback.api import create_app
from payback.config import Settings


class _FakeBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeBot:
    def __init__(self) -> None:
        self.session = _FakeBotSession()
        self.drop_pending_updates: list[bool] = []
        self.me_requested = False

    async def get_me(self) -> object:
        self.me_requested = True
        return object()

    async def delete_webhook(self, *, drop_pending_updates: bool) -> None:
        self.drop_pending_updates.append(drop_pending_updates)


class _FakeDispatcher:
    def __init__(self) -> None:
        self.started = False
        self.cancelled = False

    async def start_polling(self, _bot: _FakeBot) -> None:
        self.started = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _FakeLivePlanfixClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_lifespan_starts_polling_and_closes_resources(env: dict[str, str]) -> None:
    settings = Settings()
    bot = _FakeBot()
    dispatcher = _FakeDispatcher()
    live_client = _FakeLivePlanfixClient()
    app = create_app(
        settings,
        bot=bot,
        dispatcher=dispatcher,
        live_planfix_client=live_client,
    )

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        assert dispatcher.started is True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert bot.me_requested is True
    assert dispatcher.cancelled is True
    assert bot.drop_pending_updates == [True]
    assert bot.session.closed is True
    assert live_client.closed is True
