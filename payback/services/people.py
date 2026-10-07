"""Business rules for registration and invitation management."""

import secrets
from datetime import UTC, datetime, timedelta

from payback.db.models import Invite, User, UserRole
from payback.db.repositories.invites import InvitesRepo
from payback.db.repositories.users import UsersRepo

_INVITE_LIFETIME = timedelta(hours=72)


class ManagerRequiredError(PermissionError):
    """The requested operation requires an active local manager."""


class PeopleService:
    """Apply people-management rules using repositories supplied per update."""

    def __init__(self, users: UsersRepo, invites: InvitesRepo) -> None:
        self._users = users
        self._invites = invites

    async def create_invite(self, manager_telegram_id: int, role: UserRole) -> Invite:
        """Create a one-use 72-hour invitation for an active manager."""
        manager = await self.verify_manager(manager_telegram_id)
        return await self._invites.create(
            code=secrets.token_urlsafe(24),
            role=role,
            created_by_id=manager.id,
            expires_at=datetime.now(UTC) + _INVITE_LIFETIME,
        )

    async def verify_manager(self, telegram_id: int) -> User:
        """Return the active manager identified by a Telegram ID."""
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None or not user.is_active or user.role != UserRole.MANAGER:
            raise ManagerRequiredError("active manager required")
        return user


__all__ = ["ManagerRequiredError", "PeopleService"]
