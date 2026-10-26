"""Formatting helpers for PlanFix-facing strings.

API comments are always authored by the robot token; put the human name in the body.
"""

from payback.db.models import User


def attributed_comment(author: User, body: str) -> str:
    """Prefix a PlanFix comment with the acting Telegram user's name."""
    name = f"{author.first_name} {author.last_name}".strip()
    return f"{name}:\n{body}"


__all__ = ["attributed_comment"]
