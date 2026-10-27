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
        self.stopped = False
        self.handle_signals: bool | None = None
        self.close_bot_session: bool | None = None
        self._stop = asyncio.Event()
        self._stopped = asyncio.Event()

    async def start_polling(
        self,
        _bot: _FakeBot,
        *,
        handle_signals: bool = True,
        close_bot_session: bool = True,
        **_kwargs: object,
    ) -> None:
        self.started = True
        self.handle_signals = handle_signals
        self.close_bot_session = close_bot_session
        self._stopped.clear()
        try:
            await self._stop.wait()
            self.stopped = True
        finally:
            self._stopped.set()

    async def stop_polling(self) -> None:
        if not self.started:
            raise RuntimeError("Polling is not started")
        self._stop.set()
        await self._stopped.wait()


class _FakeLivePlanfixClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


async def test_lifespan_starts_polling_and_closes_resources(env: dict[str, str]) -> None:
    settings = Settings()
    bot = _FakeBot()
    dispatcher = _FakeDispatcher()
    live_client = _FakeLivePlanfixClient()
    engine = _FakeEngine()
    app = create_app(
        settings,
        bot=bot,
        dispatcher=dispatcher,
        live_planfix_client=live_client,
        engine=engine,  # type: ignore[arg-type]
    )

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)
        assert dispatcher.started is True
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert bot.me_requested is True
    assert dispatcher.handle_signals is False
    assert dispatcher.close_bot_session is False
    assert dispatcher.stopped is True
    assert bot.drop_pending_updates == [True]
    assert bot.session.closed is True
    assert live_client.closed is True
    assert engine.disposed is True
    assert app.state.engine is None
