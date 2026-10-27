from datetime import datetime
from decimal import Decimal

import pytest

from payback.receipts.fiscal import (
    AmbiguousFiscalQRError,
    FiscalParseError,
    parse_fiscal_qr,
    resolve_fiscal_receipt,
)


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


_FISCAL_A = "t=20261002T1153&s=890.00&fn=7284440500112233&i=40512&fp=3141592653&n=1"
_FISCAL_B = "t=20261003T1200&s=100.00&fn=1111111111111111&i=1&fp=2222222222&n=1"


def test_resolve_skips_non_fiscal_noise() -> None:
    receipt = resolve_fiscal_receipt(["https://example.com", "not-a-qr", _FISCAL_A])
    assert receipt.fn == "7284440500112233"
    assert receipt.fp == "3141592653"


def test_resolve_rejects_multiple_fiscal_payloads() -> None:
    with pytest.raises(AmbiguousFiscalQRError):
        resolve_fiscal_receipt([_FISCAL_A, "noise", _FISCAL_B])


def test_resolve_rejects_when_only_noise() -> None:
    with pytest.raises(FiscalParseError):
        resolve_fiscal_receipt(["hello", "world"])
