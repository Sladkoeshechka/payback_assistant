"""Generate deterministic synthetic receipt-image fixtures.

Run with ``.venv/bin/python scripts/generate_receipts.py`` after changing the
fixture set. The images contain invented fiscal data and never real receipts.
"""

from pathlib import Path

import cv2
import numpy as np

FIXTURES = Path(__file__).parents[1] / "tests" / "fixtures" / "receipts"
_VALID_QR = "t=20261002T1153&s=890.00&fn=7284440500112233&i=40512&fp=3141592653&n=1"
_MALFORMED_QR = "t=not-a-date&s=amount&fn=7284440500112233"


def make_receipt(payload: str) -> np.ndarray:
    """Build a receipt-like white canvas with a QR code and harmless text."""
    qr = cv2.QRCodeEncoder_create().encode(payload)
    qr = cv2.copyMakeBorder(qr, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    qr = cv2.resize(qr, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)

    canvas = np.full((1000, 800), 255, dtype=np.uint8)
    cv2.putText(canvas, "SYNTHETIC RECEIPT", (175, 90), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
    cv2.putText(
        canvas, "Not a real payment document", (175, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1
    )
    top = (canvas.shape[0] - qr.shape[0]) // 2 + 70
    left = (canvas.shape[1] - qr.shape[1]) // 2
    canvas[top : top + qr.shape[0], left : left + qr.shape[1]] = qr
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def write_image(name: str, image: np.ndarray, extension: str) -> None:
    parameters = [cv2.IMWRITE_JPEG_QUALITY, 92] if extension == ".jpg" else []
    ok, encoded = cv2.imencode(extension, image, parameters)
    if not ok:
        raise RuntimeError(f"Unable to encode {name}")
    (FIXTURES / name).write_bytes(encoded.tobytes())


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    valid = make_receipt(_VALID_QR)
    write_image("valid-receipt.jpg", valid, ".jpg")
    write_image("valid-receipt.png", valid, ".png")
    write_image("rotated-receipt.jpg", cv2.rotate(valid, cv2.ROTATE_90_CLOCKWISE), ".jpg")
    write_image("blurred-receipt.jpg", cv2.GaussianBlur(valid, (3, 3), 0), ".jpg")
    write_image("invalid-qr.jpg", make_receipt(_MALFORMED_QR), ".jpg")

    no_qr = np.full((600, 800, 3), 255, dtype=np.uint8)
    cv2.putText(
        no_qr, "SYNTHETIC RECEIPT WITHOUT QR", (90, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2
    )
    write_image("no-qr.jpg", no_qr, ".jpg")
    (FIXTURES / "corrupt-image.jpg").write_bytes(b"not an image")


if __name__ == "__main__":
    main()
