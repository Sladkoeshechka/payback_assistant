"""Domain errors raised for unsuccessful Planfix REST operations."""


class PlanfixError(RuntimeError):
    """Planfix could not complete a requested operation."""


class PlanfixScopeDenied(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The API token lacks the scope required for an operation."""


class PlanfixNotFound(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The requested Planfix resource does not exist or is inaccessible."""


class PlanfixSchemaError(PlanfixError):
    """The configured expense-card fields do not match the Planfix account."""


class PlanfixIdempotencyConflict(PlanfixError):
    """Planfix rejected a create because the Idempotency-Key was already consumed.

    Unlike standard HTTP idempotency, PlanFix does not replay the original success
    body — only this error. ``task_id`` is set when the fail payload still carries it.
    """

    def __init__(self, message: str, *, task_id: int | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id


__all__ = [
    "PlanfixError",
    "PlanfixIdempotencyConflict",
    "PlanfixNotFound",
    "PlanfixSchemaError",
    "PlanfixScopeDenied",
]
