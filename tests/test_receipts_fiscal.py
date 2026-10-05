from datetime import datetime
from decimal import Decimal

import pytest

from payback.receipts.fiscal import FiscalParseError, parse_fiscal_qr


@pytest.mark.parametrize(
    ("timestamp", "amount", "expected_datetime"),
    [
        ("20261002T1153", "890.00", datetime(2026, 10, 2, 11, 53)),
        ("20261002T11:53:06", "890,50", datetime(2026, 10, 2, 11, 53, 6)),
        ("20261002", "100", datetime(2026, 10, 2)),
    ],
)
def test_parses_fiscal_qr_date_and_amount_variants(
    timestamp: str, amount: str, expected_datetime: datetime
) -> None:
    receipt = parse_fiscal_qr(
        f"t={timestamp}&s={amount}&fn=7284440500112233&i=40512&fp=3141592653&n=1"
    )

    assert receipt.purchased_at == expected_datetime
    assert receipt.amount == Decimal(amount.replace(",", "."))
    assert receipt.fn == "7284440500112233"
    assert receipt.fd == "40512"
    assert receipt.fp == "3141592653"
    assert receipt.document_type == 1


@pytest.mark.parametrize(
    "payload",
    [
        "t=20261002T1153&s=890&fn=123&i=456&fp=789",
        "t=not-a-date&s=890&fn=123&i=456&fp=789&n=1",
        "t=20261002T1153&s=not-a-number&fn=123&i=456&fp=789&n=1",
        "t=20261002T1153&s=890&fn=123&i=456&fp=789&n=not-a-number",
    ],
)
def test_rejects_incomplete_or_invalid_fiscal_qr(payload: str) -> None:
    with pytest.raises(FiscalParseError):
        parse_fiscal_qr(payload)
