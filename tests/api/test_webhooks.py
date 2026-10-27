from datetime import date
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.api import create_app
from payback.config import Settings
from payback.db.models import ExpenseStatus, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.fakes import FakeNotifier, FakePlanfix


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


async def test_webhook_applies_status_when_deps_configured(
    env: dict[str, str], db_engine: AsyncEngine
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = Settings()
    task_id = 34
    await _pending_fixture(session_factory, task_id)

    planfix = FakePlanfix()
    planfix.seed_task(task_id, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()
    app = create_app(
        settings,
        session_factory=session_factory,
        planfix=planfix,
        notifier=notifier,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/planfix",
            json={
                "task": task_id,
                "secret": env["WEBHOOK_SECRET"],
                "status": "Одобрено",
            },
        )

    assert response.status_code == 200
    assert app.state.webhook_events == [(task_id, "Одобрено")]
    async with session_factory() as session:
        updated = await ExpensesRepo(session).get_by_planfix_task_id(task_id)
        assert updated is not None
        assert updated.status is ExpenseStatus.APPROVED
    assert len(notifier.employee_messages) == 1
    assert notifier.employee_messages[0]["status"] is ExpenseStatus.APPROVED


async def _pending_fixture(session_factory: async_sessionmaker[AsyncSession], task_id: int) -> None:
    async with session_factory() as session:
        users = UsersRepo(session)
        manager = await users.create(
            telegram_id=2000,
            first_name="Grace",
            last_name="Hopper",
            role=UserRole.MANAGER,
        )
        employee = await users.create(
            telegram_id=2001,
            first_name="Ada",
            last_name="Lovelace",
            role=UserRole.EMPLOYEE,
            manager_id=manager.id,
        )
        expenses = ExpensesRepo(session)
        expense = await expenses.create_pending_submission(
            employee_id=employee.id,
            amount=Decimal("50.00"),
            purchase_date=date(2026, 10, 2),
            category_id=7,
            category_name="Материалы",
            no_receipt=True,
        )
        await expenses.set_planfix_task(expense, task_id)
        await expenses.set_status(expense, ExpenseStatus.PENDING)
        await expenses.set_manager_message(expense, 8001)
        await session.commit()


async def test_webhook_repeat_is_idempotent(env: dict[str, str], db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = Settings()
    task_id = 44
    await _pending_fixture(session_factory, task_id)

    planfix = FakePlanfix()
    planfix.seed_task(task_id, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()
    app = create_app(
        settings,
        session_factory=session_factory,
        planfix=planfix,
        notifier=notifier,
    )
    transport = ASGITransport(app=app)
    payload = {
        "task": task_id,
        "secret": env["WEBHOOK_SECRET"],
        "status": "Одобрено",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/webhooks/planfix", json=payload)
        second = await client.post("/webhooks/planfix", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert app.state.webhook_events == [(task_id, "Одобрено"), (task_id, "Одобрено")]
    assert len(notifier.employee_messages) == 1


async def test_from_approved_to_reimbursed(env: dict[str, str], db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = Settings()
    task_id = 34
    await _pending_fixture(session_factory, task_id)

    planfix = FakePlanfix()
    planfix.seed_task(task_id, status_id=settings.planfix.statuses.approved)
    notifier = FakeNotifier()
    app = create_app(
        settings,
        session_factory=session_factory,
        planfix=planfix,
        notifier=notifier,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/planfix",
            json={
                "task": task_id,
                "secret": env["WEBHOOK_SECRET"],
                "status": "Одобрено",
            },
        )

    assert len(notifier.employee_messages) == 1
    assert notifier.employee_messages[-1]["status"] == ExpenseStatus.APPROVED

    planfix.seed_task(task_id, status_id=settings.planfix.statuses.to_pay)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/planfix",
            json={
                "task": task_id,
                "secret": env["WEBHOOK_SECRET"],
                "status": "К выплате",  # noqa: RUF001
            },
        )

    assert len(notifier.employee_messages) == 1

    planfix.seed_task(task_id, status_id=settings.planfix.statuses.reimbursed)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/webhooks/planfix",
            json={
                "task": task_id,
                "secret": env["WEBHOOK_SECRET"],
                "status": "Компенсировано",
            },
        )

    assert len(notifier.employee_messages) == 2
    assert notifier.employee_messages[-1]["status"] == ExpenseStatus.REIMBURSED
    async with session_factory() as session:
        updated = await ExpensesRepo(session).get_by_planfix_task_id(task_id)
        assert updated is not None
        assert updated.status is ExpenseStatus.REIMBURSED


async def test_webhook_apply_failure_is_logged_not_raised(
    env: dict[str, str], db_engine: AsyncEngine
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    settings = Settings()
    task_id = 66
    await _pending_fixture(session_factory, task_id)

    # Force a background processing failure: `WebhookService.apply()` will raise
    # on Planfix task fetch, but the endpoint must still answer 200 immediately.
    planfix = FakePlanfix(fail_on="get_task")
    notifier = FakeNotifier()
    app = create_app(
        settings,
        session_factory=session_factory,
        planfix=planfix,
        notifier=notifier,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/webhooks/planfix",
            json={
                "task": task_id,
                "secret": env["WEBHOOK_SECRET"],
                "status": "Одобрено",
            },
        )

    assert response.status_code == 200
    assert app.state.webhook_events == [(task_id, "Одобрено")]
