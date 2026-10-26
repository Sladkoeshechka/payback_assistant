"""Formatting helpers for PlanFix-facing strings.

API comments are always authored by the robot token; put the human name in the body.
"""

import re
from html import unescape

from payback.db.models import User

_TAG = re.compile(r"<[^>]+>")


def attributed_comment(author: User, body: str) -> str:
    """Prefix a PlanFix comment with the acting Telegram user's name."""
    name = f"{author.first_name} {author.last_name}".strip()
    return f"{name}:\n{body}"


def plain_comment_text(value: str) -> str:
    """Strip PlanFix UI HTML so comments are readable in Telegram."""
    text = value.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = _TAG.sub("", text)
    return unescape(text).replace("\xa0", " ").strip()


__all__ = ["attributed_comment", "plain_comment_text"]
