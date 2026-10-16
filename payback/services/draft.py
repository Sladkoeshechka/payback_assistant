"""In-memory expense draft carried through the submission FSM (stage 7)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class SubmissionDraft:
    """Fields collected before a local expense row is created.

    ``qr_locked`` means amount and purchase date came from a fiscal QR and must
    not be edited in the confirmation step. File bytes are optional for
    no-receipt submissions that skip a proof photo.
    """

    amount: Decimal
    purchase_date: date
    category_id: int
    category_name: str
    no_receipt: bool
    direction_id: int | None = None
    direction_name: str | None = None
    comment: str | None = None
    fn: str | None = None
    fd: str | None = None
    fp: str | None = None
    telegram_file_id: str | None = None
    image_bytes: bytes | None = None
    image_filename: str = "receipt.jpg"
    image_content_type: str = "image/jpeg"
    qr_locked: bool = False

    @property
    def has_fiscal_ids(self) -> bool:
        return bool(self.fn and self.fd and self.fp)

    @property
    def has_image(self) -> bool:
        return self.image_bytes is not None and len(self.image_bytes) > 0


__all__ = ["SubmissionDraft"]
