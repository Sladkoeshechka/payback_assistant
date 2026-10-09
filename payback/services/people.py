"""Business rules for registration and invitation management."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from payback.db.models import Invite, User, UserRole
from payback.db.repositories.invites import InvitesRepo
from payback.db.repositories.users import UsersRepo

_INVITE_LIFETIME = timedelta(hours=72)


class ManagerRequiredError(PermissionError):
    """The requested operation requires an active local manager."""


class InviteUnavailableError(ValueError):
    """An invitation is missing, expired, revoked, or already consumed."""


class AlreadyRegisteredError(ValueError):
    """The Telegram account already belongs to a local user."""


@dataclass(frozen=True, slots=True)
class InvitedRegistration:
    """Data persisted by a successful invited-user registration."""

    user: User
    invite: Invite
    inviter: User


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

    async def start_invited_registration(self, telegram_id: int, code: str) -> Invite:
        """Verify that a new Telegram user may start registration from a link."""
        if await self._users.get_by_telegram_id(telegram_id) is not None:
            raise AlreadyRegisteredError("Telegram user already registered")
        invite = await self._invites.get_active_by_code(code, datetime.now(UTC))
        if invite is None:
            raise InviteUnavailableError("invite is no longer active")
        return invite

    async def register_invited_user(
        self, telegram_id: int, full_name: str, invite_code: str
    ) -> InvitedRegistration:
        """Create a user and atomically consume the active invitation."""
        if await self._users.get_by_telegram_id(telegram_id) is not None:
            raise AlreadyRegisteredError("Telegram user already registered")
        now = datetime.now(UTC)
        invite = await self._invites.get_active_by_code(invite_code, now)
        if invite is None:
            raise InviteUnavailableError("invite is no longer active")
        inviter = await self._users.get_by_id(invite.created_by_id)
        if inviter is None:
            raise InviteUnavailableError("invite creator no longer exists")

        first_name, last_name = _split_name(full_name)
        user = await self._users.create(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            role=invite.role,
            manager_id=invite.created_by_id if invite.role == UserRole.EMPLOYEE else None,
        )
        if not await self._invites.consume_if_active(invite_code, user.id, now):
            raise InviteUnavailableError("invite was consumed concurrently")
        return InvitedRegistration(user=user, invite=invite, inviter=inviter)

    async def verify_manager(self, telegram_id: int) -> User:
        """Return the active manager identified by a Telegram ID."""
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None or not user.is_active or user.role != UserRole.MANAGER:
            raise ManagerRequiredError("active manager required")
        return user


def _split_name(value: str) -> tuple[str, str]:
    parts = value.split(maxsplit=1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("full name must include first and last names")
    return parts[0], parts[1]


__all__ = [
    "AlreadyRegisteredError",
    "InviteUnavailableError",
    "InvitedRegistration",
    "ManagerRequiredError",
    "PeopleService",
]
