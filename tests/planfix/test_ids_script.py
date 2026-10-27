"""Matching helpers used by scripts/planfix_ids.py."""

from __future__ import annotations

import sys
from pathlib import Path

from tests.conftest import load_fixture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from planfix_ids import format_report, match_fields, match_statuses  # noqa: E402


def test_match_fields_flags_duplicate_category() -> None:
    fields = load_fixture("customfields")["customfields"]
    by_key = {match.env_key: match for match in match_fields(fields)}

    assert by_key["PLANFIX_FIELD_AMOUNT"].ids == (141074,)
    assert by_key["PLANFIX_FIELD_CATEGORY"].ids == (141370, 141470)
    assert by_key["PLANFIX_FIELD_DIRECTION"].ids == (141472, 141372)


def test_match_statuses_uses_reimbursed_alias() -> None:
    statuses = load_fixture("object_statuses")["statuses"]
    by_key = {match.env_key: match for match in match_statuses(statuses)}

    assert by_key["PLANFIX_STATUS_PENDING"].ids == (101,)
    assert by_key["PLANFIX_STATUS_REIMBURSED"].ids == (108,)
    assert "компенсация завершена" in by_key["PLANFIX_STATUS_REIMBURSED"].labels[0]


def test_format_report_marks_ambiguous() -> None:
    fields = match_fields(load_fixture("customfields")["customfields"])
    statuses = match_statuses(load_fixture("object_statuses")["statuses"])
    report = format_report(
        object_id=17,
        fields=fields,
        statuses=statuses,
        unused_statuses=["0 — Черновик"],
        unmatched_directories=["999 — 'Прочее' (directoryId=1)"],
    )

    assert "PLANFIX_FIELD_AMOUNT=141074" in report
    assert "AMBIGUOUS PLANFIX_FIELD_CATEGORY=" in report
    assert "PLANFIX_STATUS_APPROVED=103" in report
    assert "0 — Черновик" in report
    assert "999 — 'Прочее'" in report


def test_match_fields_accepts_category_alias() -> None:
    fields = [
        {"id": 1, "name": "Категории расходов", "type": 9, "directoryId": 10},
        {"id": 2, "name": "Направления затрат", "type": 9, "directoryId": 11},
    ]
    by_key = {match.env_key: match for match in match_fields(fields)}
    assert by_key["PLANFIX_FIELD_CATEGORY"].ids == (1,)
    assert by_key["PLANFIX_FIELD_DIRECTION"].ids == (2,)
