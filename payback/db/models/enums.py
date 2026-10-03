from enum import StrEnum


class UserRole(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"


class ExpenseStatus(StrEnum):
    PENDING_SUBMISSION = "pending_submission"
    PENDING = "pending"
    CLARIFICATION = "clarification"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    TO_PAY = "to_pay"
    REIMBURSED = "reimbursed"
