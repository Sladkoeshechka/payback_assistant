"""Print Alembic revision, table/column layout, and row contents.

Works for any tables present — no model names are hard-coded.
Run with ``.venv/bin/python scripts/show_db.py`` (or ``make show-db``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payback.config import get_settings


def _sync_database_url(database_url: str) -> str:
    """Map async driver URLs to sync ones for ``inspect``."""
    return database_url.replace("sqlite+aiosqlite://", "sqlite://", 1).replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    )


def _describe_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        return f"{database_url}  ({Path(url.database).resolve()})"
    return database_url


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _print_schema(engine: Engine) -> list[str]:
    insp = inspect(engine)
    tables = sorted(insp.get_table_names())
    print(f"Database: {_describe_url(str(engine.url))}")
    print(f"Tables: {tables or '(none)'}\n")

    for table in tables:
        cols = insp.get_columns(table)
        fks = insp.get_foreign_keys(table)
        idxs = insp.get_indexes(table)
        print(f"## {table}")
        for col in cols:
            null = "NULL" if col.get("nullable") else "NOT NULL"
            default = col.get("default")
            default_part = f" DEFAULT {default}" if default is not None else ""
            print(f"  - {col['name']}: {col['type']} {null}{default_part}")
        for fk in fks:
            print(
                f"  FK: {fk['constrained_columns']} -> "
                f"{fk['referred_table']}.{fk['referred_columns']}"
            )
        for idx in idxs:
            uniq = " UNIQUE" if idx.get("unique") else ""
            print(f"  INDEX{uniq}: {idx['name']} on {idx['column_names']}")
        print()
    return tables


def _print_alembic(conn: Connection) -> None:
    try:
        rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
        print(f"Alembic version(s): {[row[0] for row in rows] or '(empty)'}")
    except Exception:
        print("Alembic version: (alembic_version table missing — run upgrade)")


def _print_rows(conn: Connection, tables: list[str]) -> None:
    print()
    print("== rows ==")
    if not tables:
        print("(none)")
        return
    for table in tables:
        result = conn.execute(text(f"SELECT * FROM {_quote_ident(table)}"))
        rows = result.fetchall()
        columns = list(result.keys())
        print(f"\n### {table} ({len(rows)})")
        if not rows:
            print("  (empty)")
            continue
        print(f"  columns: {columns}")
        for row in rows:
            print(f"  {dict(row._mapping)}")


def main() -> int:
    settings = get_settings()
    engine = create_engine(_sync_database_url(settings.database_url))
    try:
        tables = _print_schema(engine)
        with engine.connect() as conn:
            _print_alembic(conn)
            _print_rows(conn, tables)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
