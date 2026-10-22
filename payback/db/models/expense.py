from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from payback.db.base import Base, Timestamped
from payback.db.models.enums import ExpenseStatus

if TYPE_CHECKING:
    from payback.db.models.user import User


class Expense(Timestamped, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        Index(
            "uq_expenses_fiscal_data",
            "fn",
            "fd",
            "fp",
            unique=True,
            sqlite_where=text("fn IS NOT NULL"),
            postgresql_where=text("fn IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    planfix_task_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    status: Mapped[ExpenseStatus] = mapped_column(
        Enum(
            ExpenseStatus,
            name="expense_status",
            native_enum=False,
            create_constraint=True,
            length=18,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=ExpenseStatus.PENDING_SUBMISSION,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    purchase_date: Mapped[date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(Integer)
    category_name: Mapped[str] = mapped_column(String(255))
    direction_id: Mapped[int | None] = mapped_column(Integer)
    direction_name: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    fn: Mapped[str | None] = mapped_column(String(32))
    fd: Mapped[str | None] = mapped_column(String(32))
    fp: Mapped[str | None] = mapped_column(String(32))
    no_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    planfix_file_id: Mapped[int | None] = mapped_column(BigInteger)
    manager_message_id: Mapped[int | None] = mapped_column(BigInteger)

    employee: Mapped[User] = relationship(back_populates="expenses")
