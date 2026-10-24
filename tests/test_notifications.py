from datetime import date
from decimal import Decimal

from payback.db.models import Expense, ExpenseStatus
from payback.services.notifications import format_employee_decision


def test_format_employee_decision_escapes_html_in_detail() -> None:
    expense = Expense(
        employee_id=1,
        amount=Decimal("10.00"),
        purchase_date=date(2026, 10, 1),
        category_id=1,
        category_name="Taxi",
        no_receipt=True,
        status=ExpenseStatus.REJECTED,
        planfix_task_id=55,
    )

    text = format_employee_decision(expense=expense, detail='a <b>b</b> & "c"')

    assert "<b>" not in text
    assert "&lt;b&gt;" in text
    assert "&amp;" in text
