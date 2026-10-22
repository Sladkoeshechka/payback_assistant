from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from payback.db.base import Base, Timestamped
from payback.db.models.enums import UserRole

if TYPE_CHECKING:
    from payback.db.models.expense import Expense

class User(Timestamped, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=8,
            values_callable=lambda roles: [role.value for role in roles],
        )
    )
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    planfix_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    manager: Mapped[User | None] = relationship(
        back_populates="subordinates", remote_side="User.id", foreign_keys=[manager_id]
    )
    subordinates: Mapped[list[User]] = relationship(
        back_populates="manager", foreign_keys=[manager_id]
    )
    expenses: Mapped[list[Expense]] = relationship(back_populates="employee")
