import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from payback.db.models import Expense
from payback.logging_setup import clear_redactions

FIXTURES = Path(__file__).parent / "fixtures" / "planfix"
"""Responses captured from the real Planfix API (planfix-notes.md §9)."""


def load_fixture(name: str) -> Any:
    """Load a captured API response, with or without the .json suffix."""
    path = FIXTURES / (name if name.endswith(".json") else f"{name}.json")
    return json.loads(path.read_text(encoding="utf-8"))


#: A complete, valid environment. Tests copy and amend it rather than reading the
#: developer's own .env, so the suite never depends on local secrets.
ENV: dict[str, str] = {
    "BOT_TOKEN": "111:test-bot-token",
    "OWNER_TELEGRAM_ID": "100500",
    "WEBHOOK_SECRET": "test-webhook-secret",
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "PLANFIX_ACCOUNT": "https://example.planfix.ru",
    "PLANFIX_API_TOKEN": "test-planfix-token",
    "PLANFIX_OBJECT_ID": "17",
    "PLANFIX_FIELD_AMOUNT": "141074",
    "PLANFIX_FIELD_PURCHASE_DATE": "141076",
    "PLANFIX_FIELD_CATEGORY": "141370",
    "PLANFIX_FIELD_DIRECTION": "141372",
    "PLANFIX_FIELD_EMPLOYEE": "141374",
    "PLANFIX_FIELD_FN": "141376",
    "PLANFIX_FIELD_FD": "141378",
    "PLANFIX_FIELD_FP": "141380",
    "PLANFIX_FIELD_NO_RECEIPT": "141382",
    "PLANFIX_FIELD_PAYMENT_DATE": "141384",
    "PLANFIX_STATUS_PENDING": "101",
    "PLANFIX_STATUS_CLARIFICATION": "102",
    "PLANFIX_STATUS_APPROVED": "103",
    "PLANFIX_STATUS_REJECTED": "106",
    "PLANFIX_STATUS_NEEDS_REVISION": "109",
    "PLANFIX_STATUS_TO_PAY": "105",
    "PLANFIX_STATUS_REIMBURSED": "108",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, str]]:
    """Put a valid environment in place, isolated from the real .env file.

    Settings resolves `env_file` relative to the working directory, so running from
    an empty temporary directory is what keeps the developer's own .env — which sets
    DEV_MODE and the amount limits — out of the assertions.
    """
    monkeypatch.chdir(tmp_path)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    yield dict(ENV)


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Expense.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as database_session:
        yield database_session


@pytest.fixture(autouse=True)
def _no_leftover_redactions() -> Iterator[None]:
    yield
    clear_redactions()
