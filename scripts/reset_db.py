"""Drop and recreate all Payback tables (local wipe).

Run with ``.venv/bin/python scripts/reset_db.py --yes`` (or ``make reset-db``).
Requires an explicit ``--yes`` so a stray run cannot erase data.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.engine.url import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import payback.db.models  # noqa: F401
from payback.config import get_settings
from payback.db.base import Base
from payback.db.session import build_engine


def _describe_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        return f"{database_url}  ({Path(url.database).resolve()})"
    return database_url


async def reset() -> None:
    settings = get_settings()
    print(f"Resetting {_describe_url(settings.database_url)}")
    engine = build_engine(settings.database_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    print("Done: all tables dropped and recreated (empty).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation that you intend to wipe the database",
    )
    args = parser.parse_args(argv)
    if not args.yes:
        print("Refusing to reset without --yes", file=sys.stderr)
        return 2
    asyncio.run(reset())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
