"""Small normalized values returned by the Planfix client."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlanfixComment:
    id: int
    description: str
    owner_id: str | None


@dataclass(frozen=True, slots=True)
class PlanfixUser:
    id: int
    name: str
    last_name: str


@dataclass(frozen=True, slots=True)
class PlanfixDirectory:
    id: int
    name: str
    title_field_id: int


@dataclass(frozen=True, slots=True)
class PlanfixDirectoryEntry:
    key: int
    name: str


@dataclass(frozen=True, slots=True)
class PlanfixSchema:
    category_directory_id: int
    direction_directory_id: int


__all__ = [
    "PlanfixComment",
    "PlanfixDirectory",
    "PlanfixDirectoryEntry",
    "PlanfixSchema",
    "PlanfixUser",
]
