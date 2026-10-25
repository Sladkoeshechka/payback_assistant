"""Print PlanFix field/status ids as env lines for manual paste into the env file.

Needs only PLANFIX_ACCOUNT, PLANFIX_API_TOKEN, PLANFIX_OBJECT_ID.
Env file path: ``PAYBACK_ENV_FILE`` (same as compose), default ``.env``.

Does not write the env file — review duplicates before copying.

Run::

    export PAYBACK_ENV_FILE=$HOME/.config/payback/env
    uv run python scripts/planfix_ids.py   # or: make planfix-ids
"""

# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from payback.planfix.client import PlanfixClient
from payback.planfix.exceptions import PlanfixError, PlanfixNotFound

_DEFAULT_ENV_FILE = ".env"


def _env_file_path() -> Path:
    raw = os.environ.get("PAYBACK_ENV_FILE", _DEFAULT_ENV_FILE).strip() or _DEFAULT_ENV_FILE
    return Path(raw).expanduser()


# Expected card fields: env key → (PlanFix type id, accepted display names).
_FIELD_TARGETS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("PLANFIX_FIELD_AMOUNT", 1, ("Сумма",)),
    ("PLANFIX_FIELD_PURCHASE_DATE", 3, ("Дата покупки",)),
    (
        "PLANFIX_FIELD_CATEGORY",
        9,
        ("Категория", "Категория расходов", "Категории расходов"),
    ),
    (
        "PLANFIX_FIELD_DIRECTION",
        9,
        ("Направление затрат", "Направления затрат"),
    ),
    ("PLANFIX_FIELD_EMPLOYEE", 0, ("Сотрудник",)),
    ("PLANFIX_FIELD_FN", 0, ("ФН",)),
    ("PLANFIX_FIELD_FD", 0, ("ФД",)),
    ("PLANFIX_FIELD_FP", 0, ("ФП",)),
    ("PLANFIX_FIELD_NO_RECEIPT", 7, ("Без кассового чека",)),
    ("PLANFIX_FIELD_PAYMENT_DATE", 3, ("Дата выплаты",)),
)

# Spec names plus known account aliases (planfix-notes.md).
_STATUS_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PLANFIX_STATUS_PENDING", ("На согласовании",)),
    ("PLANFIX_STATUS_CLARIFICATION", ("Уточнение",)),
    ("PLANFIX_STATUS_APPROVED", ("Одобрено",)),
    ("PLANFIX_STATUS_REJECTED", ("Отклонено",)),
    ("PLANFIX_STATUS_NEEDS_REVISION", ("Требует доработки",)),
    ("PLANFIX_STATUS_TO_PAY", ("К выплате",)),
    ("PLANFIX_STATUS_REIMBURSED", ("Компенсировано", "компенсация завершена")),
)


class _DiscoverSettings(BaseSettings):
    """Minimal credentials — full field/status ids are what this script discovers."""

    model_config = SettingsConfigDict(extra="ignore")

    account: str = Field(validation_alias="PLANFIX_ACCOUNT")
    api_token: SecretStr = Field(validation_alias="PLANFIX_API_TOKEN")
    object_id: int = Field(validation_alias="PLANFIX_OBJECT_ID")

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "PLANFIX_ACCOUNT must include the scheme, e.g. https://acme.planfix.ru"
            )
        return value

    @property
    def rest_base_url(self) -> str:
        return f"{self.account}/rest"


def _load_settings(env_file: Path) -> _DiscoverSettings:
    if not env_file.is_file():
        raise FileNotFoundError(
            f"Env file not found: {env_file}\n"
            "Set PAYBACK_ENV_FILE to your secrets file "
            "(e.g. export PAYBACK_ENV_FILE=$HOME/.config/payback/env), "
            "or create ./.env from .env.example."
        )
    return _DiscoverSettings(_env_file=env_file)


@dataclass(frozen=True, slots=True)
class _Match:
    env_key: str
    ids: tuple[int, ...]
    labels: tuple[str, ...]


def match_fields(fields: list[dict[str, object]]) -> list[_Match]:
    results: list[_Match] = []
    for env_key, expected_type, names in _FIELD_TARGETS:
        hits = [
            field
            for field in fields
            if field.get("type") == expected_type and field.get("name") in names
        ]
        ids = tuple(int(field["id"]) for field in hits if isinstance(field.get("id"), int))
        labels = tuple(
            f"{field.get('id')} {field.get('name')!r} (directoryId={field.get('directoryId')})"
            if field.get("directoryId") is not None
            else f"{field.get('id')} {field.get('name')!r}"
            for field in hits
        )
        results.append(_Match(env_key, ids, labels))
    return results


def unmatched_directory_fields(fields: list[dict[str, object]], matched: list[_Match]) -> list[str]:
    """Hint lines for type=9 fields that did not map to CATEGORY/DIRECTION."""
    used = {field_id for match in matched for field_id in match.ids}
    lines: list[str] = []
    for field in fields:
        if field.get("type") != 9:
            continue
        field_id = field.get("id")
        if not isinstance(field_id, int) or field_id in used:
            continue
        lines.append(f"{field_id} — {field.get('name')!r} (directoryId={field.get('directoryId')})")
    return lines


def match_statuses(statuses: list[dict[str, object]]) -> list[_Match]:
    by_name: dict[str, list[int]] = {}
    for status in statuses:
        if status.get("isActive") is False:
            continue
        status_id = status.get("id")
        if not isinstance(status_id, int) or isinstance(status_id, bool):
            continue
        for label in _status_labels(status):
            by_name.setdefault(label, []).append(status_id)

    results: list[_Match] = []
    for env_key, aliases in _STATUS_TARGETS:
        ids: list[int] = []
        labels: list[str] = []
        seen: set[int] = set()
        for alias in aliases:
            for status_id in by_name.get(alias, ()):
                if status_id in seen:
                    continue
                seen.add(status_id)
                ids.append(status_id)
                labels.append(f"{status_id} ({alias})")
        results.append(_Match(env_key, tuple(ids), tuple(labels)))
    return results


def _status_labels(status: dict[str, object]) -> list[str]:
    labels: list[str] = []
    name = status.get("name")
    if isinstance(name, str) and name:
        labels.append(name)
    texts = status.get("texts")
    if isinstance(texts, list):
        for item in texts:
            if not isinstance(item, dict):
                continue
            text_name = item.get("name")
            if isinstance(text_name, str) and text_name and text_name not in labels:
                labels.append(text_name)
    return labels


def format_report(
    *,
    object_id: int,
    fields: list[_Match],
    statuses: list[_Match],
    unused_statuses: list[str],
    unmatched_directories: list[str] | None = None,
) -> str:
    lines = [
        f"# PLANFIX_OBJECT_ID={object_id}",
        "# Copy lines below into your env file after resolving AMBIGUOUS / MISSING.",
        "",
        "# --- Fields ---",
    ]
    lines.extend(_format_matches(fields))
    if unmatched_directories:
        lines.append(
            "# Unmapped directory fields (rename in PlanFix or set CATEGORY/DIRECTION by hand):"
        )
        lines.extend(f"#   {line}" for line in unmatched_directories)
    lines.append("")
    lines.append("# --- Statuses ---")
    lines.extend(_format_matches(statuses))
    if unused_statuses:
        lines.append("")
        lines.append("# Other active statuses on this object (not mapped):")
        lines.extend(f"#   {line}" for line in unused_statuses)
    return "\n".join(lines) + "\n"


def _format_matches(matches: list[_Match]) -> list[str]:
    lines: list[str] = []
    for match in matches:
        if not match.ids:
            lines.append(f"# MISSING {match.env_key}=")
        elif len(match.ids) > 1:
            lines.append(f"# AMBIGUOUS {match.env_key}=  candidates: {', '.join(match.labels)}")
            lines.append("# Pick the id that is on the «Расход» card, then uncomment one line:")
            for status_id in match.ids:
                lines.append(f"# {match.env_key}={status_id}")
        else:
            lines.append(f"{match.env_key}={match.ids[0]}")
    return lines


def _unused_status_lines(statuses: list[dict[str, object]], matched: list[_Match]) -> list[str]:
    used = {status_id for match in matched for status_id in match.ids}
    lines: list[str] = []
    for status in statuses:
        if status.get("isActive") is False:
            continue
        status_id = status.get("id")
        if not isinstance(status_id, int) or isinstance(status_id, bool):
            continue
        if status_id in used:
            continue
        labels = _status_labels(status)
        name = labels[0] if labels else "?"
        lines.append(f"{status_id} — {name}")
    return lines


def _format_objects(objects: list[dict[str, object]]) -> str:
    if not objects:
        return "(API returned no objects)"
    lines = []
    for item in objects:
        object_id = item.get("id")
        name = item.get("name") or "?"
        lines.append(f"  {object_id}: {name}")
    return "\n".join(lines)


async def _run() -> int:
    env_file = _env_file_path()
    settings = _load_settings(env_file)
    print(f"# Reading credentials from {env_file.resolve()}", file=sys.stderr)

    async with PlanfixClient(settings) as client:  # type: ignore[arg-type]
        fields = await client.get_task_custom_fields()
        objects = await client.list_objects()
        try:
            statuses = await client.list_object_statuses()
        except (PlanfixNotFound, PlanfixError) as error:
            print(
                f"PLANFIX_OBJECT_ID={settings.object_id} is not a valid REST Object id "
                f"({error}).\n"
                "The objectId in the PlanFix UI URL is often NOT the REST id.\n"
                "Set PLANFIX_OBJECT_ID to one of these (from POST /object/list):\n"
                f"{_format_objects(objects)}\n"
                "Hint: look for «Расход». Or open any Расход task via API and read "
                "task.object.id.",
                file=sys.stderr,
            )
            return 2

    field_matches = match_fields(fields)
    status_matches = match_statuses(statuses)
    print(
        format_report(
            object_id=settings.object_id,
            fields=field_matches,
            statuses=status_matches,
            unused_statuses=_unused_status_lines(statuses, status_matches),
            unmatched_directories=unmatched_directory_fields(fields, field_matches),
        ),
        end="",
    )
    missing_or_ambiguous = any(len(m.ids) != 1 for m in field_matches + status_matches)
    return 1 if missing_or_ambiguous else 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
