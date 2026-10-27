import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from payback.db.models import User, UserRole


async def assert_upgraded_schema_works(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_table_names()
            )
        assert set(tables) >= {"alembic_version", "expenses", "invites", "users"}

        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.add(
                User(
                    telegram_id=1000,
                    first_name="Grace",
                    last_name="Hopper",
                    role=UserRole.MANAGER,
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


def test_upgrade_head_creates_usable_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'payback.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))

    command.upgrade(config, "head")

    asyncio.run(assert_upgraded_schema_works(database_url))
