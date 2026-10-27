"""Build Planfix task names and custom-field payloads for an expense card."""

from decimal import Decimal

from payback.config import PlanfixFieldIds
from payback.db.models import Expense
from payback.planfix import fields as planfix_fields
from payback.services.draft import SubmissionDraft


def task_name(*, amount: Decimal, category_name: str, employee_name: str) -> str:
    """Format the Planfix task title."""
    return f"Расход: {_format_amount(amount)} ₽, {category_name} — {employee_name}"


def employee_display_name(*, first_name: str, last_name: str) -> str:
    return f"{first_name} {last_name}"


def custom_field_data_for_draft(
    draft: SubmissionDraft,
    *,
    employee_name: str,
    field_ids: PlanfixFieldIds,
) -> list[dict[str, object]]:
    """Serialize a draft into Planfix ``customFieldData``."""
    if draft.amount is None or draft.purchase_date is None or draft.category_id is None:
        raise ValueError("submission draft is incomplete")
    values: dict[int, planfix_fields.FieldValue | None] = {
        field_ids.amount: planfix_fields.number(draft.amount),
        field_ids.purchase_date: planfix_fields.date_value(draft.purchase_date),
        field_ids.category: planfix_fields.directory_value(draft.category_id),
        field_ids.direction: (
            planfix_fields.directory_value(draft.direction_id)
            if draft.direction_id is not None
            else None
        ),
        field_ids.employee: employee_name,
        field_ids.fn: draft.fn,
        field_ids.fd: draft.fd,
        field_ids.fp: draft.fp,
        field_ids.no_receipt: draft.no_receipt,
        field_ids.payment_date: None,
    }
    return planfix_fields.custom_fields(values)


def custom_field_data_for_expense(
    expense: Expense,
    *,
    employee_name: str,
    field_ids: PlanfixFieldIds,
) -> list[dict[str, object]]:
    """Serialize a persisted expense into Planfix ``customFieldData``."""
    draft = SubmissionDraft(
        amount=expense.amount,
        purchase_date=expense.purchase_date,
        category_id=expense.category_id,
        category_name=expense.category_name,
        no_receipt=expense.no_receipt,
        direction_id=expense.direction_id,
        direction_name=expense.direction_name,
        comment=expense.comment,
        fn=expense.fn,
        fd=expense.fd,
        fp=expense.fp,
        telegram_file_id=expense.telegram_file_id,
    )
    return custom_field_data_for_draft(draft, employee_name=employee_name, field_ids=field_ids)


def _format_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    return f"{quantized:,.2f}".replace(",", " ").replace(".", ",")


__all__ = [
    "custom_field_data_for_draft",
    "custom_field_data_for_expense",
    "employee_display_name",
    "task_name",
]
