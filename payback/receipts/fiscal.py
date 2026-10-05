"""Parsing of fiscal-receipt QR payloads."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl


class FiscalParseError(ValueError):
    """A QR value does not contain a complete fiscal receipt payload."""


@dataclass(frozen=True, slots=True)
class FiscalReceipt:
    """The values the bot needs from a Russian fiscal receipt QR code."""

    purchased_at: datetime
    amount: Decimal
    fn: str
    fd: str
    fp: str
    document_type: int


_DATE_FORMATS = (
    ("%Y%m%dT%H%M%S", 15),
    ("%Y%m%dT%H%M", 13),
    ("%Y%m%dT%H:%M:%S", 17),
    ("%Y%m%dT%H:%M", 14),
    ("%Y%m%d", 8),
)
_REQUIRED_KEYS = frozenset({"t", "s", "fn", "i", "fp", "n"})


def parse_fiscal_qr(value: str) -> FiscalReceipt:
    """Parse a fiscal QR query string, accepting common date and amount variants."""
    fields = dict(parse_qsl(value.strip(), keep_blank_values=True))
    missing = sorted(key for key in _REQUIRED_KEYS if not fields.get(key))
    if missing:
        raise FiscalParseError(f"Fiscal QR is missing required fields: {', '.join(missing)}")

    return FiscalReceipt(
        purchased_at=_parse_datetime(fields["t"]),
        amount=_parse_amount(fields["s"]),
        fn=fields["fn"],
        fd=fields["i"],
        fp=fields["fp"],
        document_type=_parse_document_type(fields["n"]),
    )


def _parse_datetime(value: str) -> datetime:
    for date_format, expected_length in _DATE_FORMATS:
        if len(value) != expected_length:
            continue
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    raise FiscalParseError(f"Unsupported fiscal receipt date: {value!r}")


def _parse_amount(value: str) -> Decimal:
    try:
        amount = Decimal(value.strip().replace(",", "."))
    except InvalidOperation as error:
        raise FiscalParseError(f"Invalid fiscal receipt amount: {value!r}") from error
    if not amount.is_finite():
        raise FiscalParseError(f"Invalid fiscal receipt amount: {value!r}")
    return amount


def _parse_document_type(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise FiscalParseError(f"Invalid fiscal document type: {value!r}") from error


__all__ = ["FiscalParseError", "FiscalReceipt", "parse_fiscal_qr"]
