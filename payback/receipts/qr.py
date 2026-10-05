"""QR decoders for receipt images.

OpenCV is the required implementation. ZBar is deliberately optional because
``pyzbar`` needs the operating-system ``libzbar.so`` library.
"""

import asyncio
from collections.abc import Iterable
from typing import Protocol

import cv2
import numpy as np


class QRCodeNotFoundError(ValueError):
    """No readable QR code was found by any enabled decoder."""


class QRDecoderUnavailableError(RuntimeError):
    """An optional QR decoder is enabled without its native dependency."""


class QRDecoder(Protocol):
    """A synchronous image decoder run outside the event loop."""

    def decode(self, image: bytes) -> str | None: ...


class OpenCVQRCodeDecoder:
    """Decode QR codes with OpenCV, which has no system-library dependency."""

    def decode(self, image: bytes) -> str | None:
        matrix = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if matrix is None:
            return None
        try:
            value, _, _ = cv2.QRCodeDetector().detectAndDecode(matrix)
        except cv2.error:
            return None
        return value or None


class PyzbarQRCodeDecoder:
    """Optional ZBar implementation for receipt photos OpenCV cannot read."""

    def decode(self, image: bytes) -> str | None:
        try:
            from pyzbar.pyzbar import decode
        except (ImportError, OSError) as error:
            raise QRDecoderUnavailableError(
                "pyzbar requires the optional zbar dependency and libzbar.so"
            ) from error

        matrix = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if matrix is None:
            return None
        matches = decode(matrix)
        if not matches:
            return None
        encoded_value = matches[0].data
        if not isinstance(encoded_value, bytes):
            return None
        try:
            return encoded_value.decode("utf-8")
        except UnicodeDecodeError:
            return None


async def decode_qr(image: bytes, decoders: Iterable[QRDecoder] = (OpenCVQRCodeDecoder(),)) -> str:
    """Try enabled decoders in a worker thread and return the first QR payload."""
    for decoder in decoders:
        value = await asyncio.to_thread(decoder.decode, image)
        if value is not None:
            return value
    raise QRCodeNotFoundError("QR code was not found or could not be read")


__all__ = [
    "OpenCVQRCodeDecoder",
    "PyzbarQRCodeDecoder",
    "QRCodeNotFoundError",
    "QRDecoder",
    "QRDecoderUnavailableError",
    "decode_qr",
]
