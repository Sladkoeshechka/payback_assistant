"""Receipt image recognition, fiscal QR parsing, and validation."""

from payback.receipts.fiscal import FiscalParseError, FiscalReceipt, parse_fiscal_qr
from payback.receipts.qr import (
    OpenCVQRCodeDecoder,
    PyzbarQRCodeDecoder,
    QRCodeNotFoundError,
    QRDecoderUnavailableError,
    decode_qr,
)
from payback.receipts.validation import ReceiptValidationError, validate_image, validate_receipt

__all__ = [
    "FiscalParseError",
    "FiscalReceipt",
    "OpenCVQRCodeDecoder",
    "PyzbarQRCodeDecoder",
    "QRCodeNotFoundError",
    "QRDecoderUnavailableError",
    "ReceiptValidationError",
    "decode_qr",
    "parse_fiscal_qr",
    "validate_image",
    "validate_receipt",
]
