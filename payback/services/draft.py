"""In-memory expense draft carried through the submission FSM (stage 7)."""

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class SubmissionDraft:
    """Fields collected before a local expense row is created.

    ``qr_locked`` means amount and purchase date came from a fiscal QR and must
    not be edited in the confirmation step. File bytes may be filled just before
    submit (downloaded from Telegram); FSM storage keeps only ``telegram_file_id``.
    """

    amount: Decimal | None = None
    purchase_date: date | None = None
    category_id: int | None = None
    category_name: str | None = None
    no_receipt: bool = False
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
        if self.telegram_file_id:
            return True
        return self.image_bytes is not None and len(self.image_bytes) > 0

    def to_fsm_data(self) -> dict[str, Any]:
        """JSON-friendly snapshot (no image bytes) for aiogram FSM storage."""
        payload = asdict(self)
        payload.pop("image_bytes", None)
        if self.amount is not None:
            payload["amount"] = str(self.amount)
        if self.purchase_date is not None:
            payload["purchase_date"] = self.purchase_date.isoformat()
        return payload

    @classmethod
    def from_fsm_data(cls, data: dict[str, Any]) -> "SubmissionDraft":
        amount = data.get("amount")
        purchase_date = data.get("purchase_date")
        return cls(
            amount=Decimal(amount) if amount is not None else None,
            purchase_date=date.fromisoformat(purchase_date) if purchase_date else None,
            category_id=data.get("category_id"),
            category_name=data.get("category_name"),
            no_receipt=bool(data.get("no_receipt", False)),
            direction_id=data.get("direction_id"),
            direction_name=data.get("direction_name"),
            comment=data.get("comment"),
            fn=data.get("fn"),
            fd=data.get("fd"),
            fp=data.get("fp"),
            telegram_file_id=data.get("telegram_file_id"),
            image_filename=data.get("image_filename") or "receipt.jpg",
            image_content_type=data.get("image_content_type") or "image/jpeg",
            qr_locked=bool(data.get("qr_locked", False)),
        )


__all__ = ["SubmissionDraft"]
