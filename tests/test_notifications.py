from datetime import date
from decimal import Decimal

from payback.db.models import Expense, ExpenseStatus
from payback.services.notifications import (
    NOTIFY_EMPLOYEE_NEEDS_REVISION,
    format_employee_decision,
)
from payback.services.planfix_text import plain_comment_text


def _expense(status: ExpenseStatus) -> Expense:
    return Expense(
        employee_id=1,
        amount=Decimal("10.00"),
        purchase_date=date(2026, 10, 1),
        category_id=1,
        category_name="Taxi",
        no_receipt=True,
        status=status,
        planfix_task_id=55,
    )


def test_format_employee_decision_escapes_html_in_detail() -> None:
    text = format_employee_decision(
        expense=_expense(ExpenseStatus.REJECTED),
        detail='a <b>b</b> & "c"',
    )

    assert "<b>" not in text
    assert "&lt;b&gt;" in text
    assert "&amp;" in text


def test_format_employee_decision_needs_revision_includes_detail() -> None:
    text = format_employee_decision(
        expense=_expense(ExpenseStatus.NEEDS_REVISION),
        detail="приложите чек",
    )

    assert text == NOTIFY_EMPLOYEE_NEEDS_REVISION.format(
        task_id=55, detail="приложите чек"
    )


def test_format_employee_decision_needs_revision_without_detail() -> None:
    text = format_employee_decision(expense=_expense(ExpenseStatus.NEEDS_REVISION))

    assert "По заявке №55 нужна доработка." in text
    assert "Ответьте текстом или фото в этот чат." in text
    assert "—" not in text


def test_plain_comment_text_strips_planfix_html() -> None:
    assert plain_comment_text("<p>нужен&nbsp;чек<br/>пожалуйста</p>") == "нужен чек\nпожалуйста"
