"""Domain errors raised for unsuccessful Planfix REST operations."""


class PlanfixError(RuntimeError):
    """Planfix could not complete a requested operation."""


class PlanfixScopeDenied(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The API token lacks the scope required for an operation."""


class PlanfixNotFound(PlanfixError):  # noqa: N818 - public name follows the project specification.
    """The requested Planfix resource does not exist or is inaccessible."""


class PlanfixSchemaError(PlanfixError):
    """The configured expense-card fields do not match the Planfix account."""


__all__ = ["PlanfixError", "PlanfixNotFound", "PlanfixSchemaError", "PlanfixScopeDenied"]
