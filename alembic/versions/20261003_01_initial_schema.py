"""Create the initial Payback schema.

Revision ID: 20261003_01
Revises:
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261003_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_user_role = sa.Enum(
    "employee",
    "manager",
    name="user_role",
    native_enum=False,
    create_constraint=True,
    length=8,
)
_expense_status = sa.Enum(
    "pending_submission",
    "pending",
    "clarification",
    "approved",
    "rejected",
    "needs_revision",
    "to_pay",
    "reimbursed",
    name="expense_status",
    native_enum=False,
    create_constraint=True,
    length=18,
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=False),
        sa.Column("role", _user_role, nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("planfix_user_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_users_manager_id", "users", ["manager_id"])
    op.create_index("ix_users_planfix_user_id", "users", ["planfix_user_id"], unique=True)
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("role", _user_role, nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_by_id", sa.Integer(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["used_by_id"], ["users.id"]),
    )
    op.create_index("ix_invites_code", "invites", ["code"], unique=True)
    op.create_index("ix_invites_created_by_id", "invites", ["created_by_id"])
    op.create_index("ix_invites_used_by_id", "invites", ["used_by_id"])

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("planfix_task_id", sa.BigInteger(), nullable=True),
        sa.Column("status", _expense_status, nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("category_name", sa.String(length=255), nullable=False),
        sa.Column("direction_id", sa.Integer(), nullable=True),
        sa.Column("direction_name", sa.String(length=255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("fn", sa.String(length=32), nullable=True),
        sa.Column("fd", sa.String(length=32), nullable=True),
        sa.Column("fp", sa.String(length=32), nullable=True),
        sa.Column("no_receipt", sa.Boolean(), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=255), nullable=True),
        sa.Column("planfix_file_id", sa.BigInteger(), nullable=True),
        sa.Column("manager_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"]),
    )
    op.create_index("ix_expenses_employee_id", "expenses", ["employee_id"])
    op.create_index("ix_expenses_planfix_task_id", "expenses", ["planfix_task_id"], unique=True)
    op.create_index("ix_expenses_status", "expenses", ["status"])
    op.create_index(
        "uq_expenses_fiscal_data",
        "expenses",
        ["fn", "fd", "fp"],
        unique=True,
        sqlite_where=sa.text("fn IS NOT NULL"),
        postgresql_where=sa.text("fn IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_expenses_fiscal_data", table_name="expenses")
    op.drop_index("ix_expenses_status", table_name="expenses")
    op.drop_index("ix_expenses_planfix_task_id", table_name="expenses")
    op.drop_index("ix_expenses_employee_id", table_name="expenses")
    op.drop_table("expenses")

    op.drop_index("ix_invites_used_by_id", table_name="invites")
    op.drop_index("ix_invites_created_by_id", table_name="invites")
    op.drop_index("ix_invites_code", table_name="invites")
    op.drop_table("invites")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_index("ix_users_planfix_user_id", table_name="users")
    op.drop_index("ix_users_manager_id", table_name="users")
    op.drop_table("users")
