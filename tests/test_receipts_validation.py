from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from payback.config import Settings
from payback.receipts.fiscal import FiscalReceipt
from payback.receipts.validation import (
    MAX_RECEIPT_IMAGE_BYTES,
    ReceiptValidationError,
    validate_amount,
    validate_image,
    validate_purchase_date,
    validate_receipt,
)

_RECEIPTS = Path(__file__).parent / "fixtures" / "receipts"


def test_accepts_valid_jpeg_and_png() -> None:
    validate_image((_RECEIPTS / "valid-receipt.jpg").read_bytes(), "image/jpeg")
    validate_image((_RECEIPTS / "valid-receipt.png").read_bytes(), "image/png")


@pytest.mark.parametrize(
    ("name", "content_type"),
    [
        ("valid-receipt.jpg", "application/pdf"),
        ("corrupt-image.jpg", "image/jpeg"),
        ("valid-receipt.png", None),
    ],
)
def test_rejects_unsupported_or_invalid_image(name: str, content_type: str | None) -> None:
    with pytest.raises(ReceiptValidationError, match="JPG или PNG"):
        validate_image((_RECEIPTS / name).read_bytes(), content_type)


def test_rejects_image_above_size_limit() -> None:
    with pytest.raises(ReceiptValidationError, match="JPG или PNG"):
        validate_image(b"x" * (MAX_RECEIPT_IMAGE_BYTES + 1), "image/jpeg")


def test_validates_qr_receipt_amount_and_date(env: dict[str, str]) -> None:
    settings = Settings()
    receipt = FiscalReceipt(
        purchased_at=datetime(2026, 10, 2, 11, 53),
        amount=Decimal("890.00"),
        fn="7284440500112233",
        fd="40512",
        fp="3141592653",
        document_type=1,
    )

    validate_receipt(receipt, settings, today=date(2026, 10, 4))


@pytest.mark.parametrize(
    ("amount", "message"),
    [
        (Decimal("0"), "Сумма должна быть от 0,01 до 100 000,00 ₽"),
        (Decimal("100000.01"), "Сумма должна быть от 0,01 до 100 000,00 ₽"),
    ],
)
def test_rejects_amount_outside_limit(env: dict[str, str], amount: Decimal, message: str) -> None:
    with pytest.raises(ReceiptValidationError, match=message):
        validate_amount(amount, Settings())


def test_rejects_future_and_too_old_purchase_dates(env: dict[str, str]) -> None:
    settings = Settings()
    today = date(2026, 10, 4)

    with pytest.raises(ReceiptValidationError, match="не может быть в будущем"):
        validate_purchase_date(today + timedelta(days=1), settings, today=today)
    with pytest.raises(ReceiptValidationError, match="Чек старше 90 дней"):
        validate_purchase_date(today - timedelta(days=91), settings, today=today)
    validate_purchase_date(today - timedelta(days=90), settings, today=today)


def test_no_receipt_amount_cap(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_RECEIPT_MAX_AMOUNT", "1000")

    with pytest.raises(ReceiptValidationError, match="Без чека можно подать трату до 1 000,00 ₽"):
        validate_amount(Decimal("1000.01"), Settings(), no_receipt=True)
