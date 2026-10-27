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


def _dedupe_payloads(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _decode_image_matrix(image: bytes) -> np.ndarray | None:
    """Decode image bytes; empty buffers raise in OpenCV 5, so guard first."""
    if not image:
        return None
    return cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)


class OpenCVQRCodeDecoder:
    """Decode QR codes with OpenCV, which has no system-library dependency."""

    def decode(self, image: bytes) -> list[str]:
        matrix = _decode_image_matrix(image)
        if matrix is None:
            return []
        detector = cv2.QRCodeDetector()
        # Single-QR path is more reliable on real phone photos; multi is for several codes.
        payloads = _dedupe_payloads(_opencv_decode_single(detector, matrix))
        if payloads:
            return payloads
        return _dedupe_payloads(_opencv_decode_multi(detector, matrix))


def _opencv_decode_single(detector: cv2.QRCodeDetector, matrix: np.ndarray) -> list[str]:
    try:
        value, _, _ = detector.detectAndDecode(matrix)
    except cv2.error:
        return []
    return [value] if value else []


def _opencv_decode_multi(detector: cv2.QRCodeDetector, matrix: np.ndarray) -> list[str]:
    try:
        ok, values, _, _ = detector.detectAndDecodeMulti(matrix)
    except cv2.error:
        return []
    if not ok:
        return []
    return [value for value in values if value]


class PyzbarQRCodeDecoder:
    """Optional ZBar implementation for receipt photos OpenCV cannot read."""

    def decode(self, image: bytes) -> list[str]:
        decode = _import_pyzbar_decode()
        matrix = _decode_image_matrix(image)
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
        return _dedupe_payloads(payloads)


def _import_pyzbar_decode():
    try:
        from pyzbar.pyzbar import decode
    except (ImportError, OSError) as error:
        raise QRDecoderUnavailableError(
            "pyzbar requires the optional zbar dependency and libzbar.so"
        ) from error
    return decode


_default_decoders: tuple[QRDecoder, ...] | None = None


def default_qr_decoders() -> tuple[QRDecoder, ...]:
    """OpenCV plus pyzbar when the optional zbar stack is available."""
    global _default_decoders
    if _default_decoders is not None:
        return _default_decoders
    decoders: list[QRDecoder] = [OpenCVQRCodeDecoder()]
    try:
        _import_pyzbar_decode()
    except QRDecoderUnavailableError:
        pass
    else:
        decoders.append(PyzbarQRCodeDecoder())
    _default_decoders = tuple(decoders)
    return _default_decoders


async def decode_qr(
    image: bytes,
    decoders: Iterable[QRDecoder] | None = None,
) -> list[str]:
    """Try enabled decoders in a worker thread; return every payload from the first hit."""
    chain = default_qr_decoders() if decoders is None else decoders
    for decoder in chain:
        values = await asyncio.to_thread(decoder.decode, image)
        if values:
            return _dedupe_payloads(values)
    raise QRCodeNotFoundError("QR code was not found or could not be read")


__all__ = [
    "OpenCVQRCodeDecoder",
    "PyzbarQRCodeDecoder",
    "QRCodeNotFoundError",
    "QRDecoder",
    "QRDecoderUnavailableError",
    "decode_qr",
    "default_qr_decoders",
]
