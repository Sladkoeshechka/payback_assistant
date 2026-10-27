"""Receipt image recognition, fiscal QR parsing, and validation."""

from payback.receipts.fiscal import (
    AmbiguousFiscalQRError,
    FiscalParseError,
    FiscalReceipt,
    parse_fiscal_qr,
    resolve_fiscal_receipt,
)
from payback.receipts.qr import (
    OpenCVQRCodeDecoder,
    PyzbarQRCodeDecoder,
    QRCodeNotFoundError,
    QRDecoderUnavailableError,
    decode_qr,
)
from payback.receipts.validation import ReceiptValidationError, validate_image, validate_receipt

__all__ = [
    "AmbiguousFiscalQRError",
    "FiscalParseError",
    "FiscalReceipt",
    "OpenCVQRCodeDecoder",
    "PyzbarQRCodeDecoder",
    "QRCodeNotFoundError",
    "QRDecoderUnavailableError",
    "ReceiptValidationError",
    "decode_qr",
    "parse_fiscal_qr",
    "resolve_fiscal_receipt",
    "validate_image",
    "validate_receipt",
]
