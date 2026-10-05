"""Validation shared by QR-recognized and manually entered expenses."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from payback.config import Settings
from payback.receipts.fiscal import FiscalReceipt

MAX_RECEIPT_IMAGE_BYTES = 15 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png"})


class ReceiptValidationError(ValueError):
    """A receipt or manually entered value violates the product rules."""


def validate_image(image: bytes, content_type: str | None) -> None:
    """Require a decodable JPEG or PNG within Telegram's receipt-file limit."""
    if content_type not in _ALLOWED_IMAGE_TYPES or len(image) > MAX_RECEIPT_IMAGE_BYTES:
        raise ReceiptValidationError("Пришлите фото чека в формате JPG или PNG")
    try:
        with Image.open(BytesIO(image)) as opened:
            if opened.format not in {"JPEG", "PNG"}:
                raise ReceiptValidationError("Пришлите фото чека в формате JPG или PNG")
            opened.verify()
    except (UnidentifiedImageError, OSError) as error:
        raise ReceiptValidationError("Пришлите фото чека в формате JPG или PNG") from error


def validate_receipt(
    receipt: FiscalReceipt, settings: Settings, *, today: date | None = None
) -> None:
    """Validate amount and purchase date against configured expense limits."""
    validate_amount(receipt.amount, settings)
    validate_purchase_date(receipt.purchased_at.date(), settings, today=today)


def validate_amount(amount: Decimal, settings: Settings, *, no_receipt: bool = False) -> None:
    """Check a manual or QR-derived amount, including the optional no-receipt cap."""
    if not amount.is_finite() or amount <= 0 or amount > settings.max_amount:
        raise ReceiptValidationError(
            f"Сумма должна быть от 0,01 до {_format_amount(settings.max_amount)} ₽"
        )
    if (
        no_receipt
        and settings.no_receipt_max_amount is not None
        and amount > settings.no_receipt_max_amount
    ):
        raise ReceiptValidationError(
            f"Без чека можно подать трату до {_format_amount(settings.no_receipt_max_amount)} ₽"
        )


def validate_purchase_date(
    purchase_date: date, settings: Settings, *, today: date | None = None
) -> None:
    """Reject purchases from the future and receipts older than the configured age."""
    current_date = today or date.today()
    if purchase_date > current_date:
        raise ReceiptValidationError("Дата покупки не может быть в будущем")
    if (current_date - purchase_date).days > settings.max_receipt_age_days:
        raise ReceiptValidationError(
            f"Чек старше {settings.max_receipt_age_days} дней. Обратитесь к руководителю"
        )


def _format_amount(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


__all__ = [
    "MAX_RECEIPT_IMAGE_BYTES",
    "ReceiptValidationError",
    "validate_amount",
    "validate_image",
    "validate_purchase_date",
    "validate_receipt",
]
