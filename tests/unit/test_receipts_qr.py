from collections.abc import Iterator
from pathlib import Path

import pytest

from payback.receipts.fiscal import FiscalParseError, parse_fiscal_qr
from payback.receipts.qr import QRCodeNotFoundError, decode_qr

_RECEIPTS = Path(__file__).resolve().parents[1] / "fixtures" / "receipts"
_EXPECTED_QR = "t=20261002T1153&s=890.00&fn=7284440500112233&i=40512&fp=3141592653&n=1"


@pytest.fixture
def receipt_image() -> Iterator[Path]:
    yield _RECEIPTS


@pytest.mark.parametrize(
    "name",
    ["valid-receipt.jpg", "valid-receipt.png", "rotated-receipt.jpg", "blurred-receipt.jpg"],
)
async def test_opencv_decodes_synthetic_receipt_images(receipt_image: Path, name: str) -> None:
    assert await decode_qr((receipt_image / name).read_bytes()) == [_EXPECTED_QR]


@pytest.mark.parametrize("name", ["no-qr.jpg", "corrupt-image.jpg"])
async def test_invalid_images_report_no_qr(receipt_image: Path, name: str) -> None:
    with pytest.raises(QRCodeNotFoundError):
        await decode_qr((receipt_image / name).read_bytes())


async def test_qr_with_malformed_fiscal_data_is_decoded_then_rejected(receipt_image: Path) -> None:
    qr_values = await decode_qr((receipt_image / "invalid-qr.jpg").read_bytes())

    with pytest.raises(FiscalParseError):
        parse_fiscal_qr(qr_values[0])


async def test_decode_qr_uses_first_decoder_that_returns_payloads() -> None:
    class Empty:
        def decode(self, image: bytes) -> list[str]:
            return []

    class Hit:
        def decode(self, image: bytes) -> list[str]:
            return ["noise", _EXPECTED_QR]

    assert await decode_qr(b"ignored", decoders=(Empty(), Hit())) == ["noise", _EXPECTED_QR]
