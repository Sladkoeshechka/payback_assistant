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

    def decode(self, image: bytes) -> list[str]: ...


class OpenCVQRCodeDecoder:
    """Decode QR codes with OpenCV, which has no system-library dependency."""

    def decode(self, image: bytes) -> list[str]:
        matrix = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if matrix is None:
            return []
        try:
            ok, values, _, _ = cv2.QRCodeDetector().detectAndDecodeMulti(matrix)
        except cv2.error:
            return []
        if not ok:
            return []
        return [value for value in values if value]


class PyzbarQRCodeDecoder:
    """Optional ZBar implementation for receipt photos OpenCV cannot read."""

    def decode(self, image: bytes) -> list[str]:
        try:
            from pyzbar.pyzbar import decode
        except (ImportError, OSError) as error:
            raise QRDecoderUnavailableError(
                "pyzbar requires the optional zbar dependency and libzbar.so"
            ) from error

        matrix = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if matrix is None:
            return []
        payloads: list[str] = []
        for match in decode(matrix):
            encoded_value = match.data
            if not isinstance(encoded_value, bytes):
                continue
            try:
                payloads.append(encoded_value.decode("utf-8"))
            except UnicodeDecodeError:
                continue
        return payloads


async def decode_qr(
    image: bytes, decoders: Iterable[QRDecoder] = (OpenCVQRCodeDecoder(),)
) -> list[str]:
    """Try enabled decoders in a worker thread; return every payload from the first hit."""
    for decoder in decoders:
        values = await asyncio.to_thread(decoder.decode, image)
        if values:
            return values
    raise QRCodeNotFoundError("QR code was not found or could not be read")


__all__ = [
    "OpenCVQRCodeDecoder",
    "PyzbarQRCodeDecoder",
    "QRCodeNotFoundError",
    "QRDecoder",
    "QRDecoderUnavailableError",
    "decode_qr",
]
