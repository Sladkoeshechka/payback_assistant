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


class EmployeeRequiredError(PermissionError):
    """The requested operation requires an active local employee."""


class InviteUnavailableError(ValueError):
    """An invitation is missing, expired, revoked, or already consumed."""


class AlreadyRegisteredError(ValueError):
    """The Telegram account already belongs to a local user."""


class StaffMemberNotFoundError(LookupError):
    """A staff action targeted a user the manager cannot manage."""


class InviteNotFoundError(LookupError):
    """A staff action targeted an invitation the manager does not own."""


class PlanfixLinkConflictError(ValueError):
    """Another local user already claims this Planfix account."""


@dataclass(frozen=True, slots=True)
class InvitedRegistration:
    """Data persisted by a successful invited-user registration."""

    user: User
    invite: Invite
    inviter: User


@dataclass(frozen=True, slots=True)
class StaffOverview:
    """Manager-facing snapshot for the ``/staff`` screen."""

    manager: User
    subordinates: tuple[User, ...]
    invites: tuple[Invite, ...]


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

    async def get_staff_overview(self, manager_telegram_id: int) -> StaffOverview:
        """Return subordinates (incl. inactive) and unused invites owned by this manager."""
        manager = await self.verify_manager(manager_telegram_id)
        subordinates = await self._users.list_subordinates(manager.id)
        invites = await self._invites.list_active_for_creator(manager.id, datetime.now(UTC))
        return StaffOverview(
            manager=manager,
            subordinates=tuple(subordinates),
            invites=tuple(invites),
        )

    async def revoke_invite(self, manager_telegram_id: int, invite_id: int) -> Invite:
        """Revoke an unused invitation created by this manager."""
        manager = await self.verify_manager(manager_telegram_id)
        invite = await self._invites.get_by_id(invite_id)
        if (
            invite is None
            or invite.created_by_id != manager.id
            or invite.used_at is not None
            or invite.revoked_at is not None
        ):
            raise InviteNotFoundError("invite is not available to revoke")
        await self._invites.revoke(invite, datetime.now(UTC))
        return invite

    async def deactivate_subordinate(self, manager_telegram_id: int, employee_id: int) -> User:
        """Deactivate an active employee who reports to this manager."""
        manager = await self.verify_manager(manager_telegram_id)
        employee = await self._users.get_by_id(employee_id)
        if (
            employee is None
            or employee.manager_id != manager.id
            or employee.role != UserRole.EMPLOYEE
            or not employee.is_active
        ):
            raise StaffMemberNotFoundError("subordinate is not available to deactivate")
        await self._users.set_active(employee, False)
        return employee

    async def reactivate_subordinate(self, manager_telegram_id: int, employee_id: int) -> User:
        """Re-enable an inactive employee who reports to this manager."""
        manager = await self.verify_manager(manager_telegram_id)
        employee = await self._users.get_by_id(employee_id)
        if (
            employee is None
            or employee.manager_id != manager.id
            or employee.role != UserRole.EMPLOYEE
            or employee.is_active
        ):
            raise StaffMemberNotFoundError("subordinate is not available to reactivate")
        await self._users.set_active(employee, True)
        return employee

    async def list_transfer_targets(self, manager_telegram_id: int) -> list[User]:
        """Active managers other than the caller — candidates to receive a subordinate."""
        manager = await self.verify_manager(manager_telegram_id)
        return await self._users.list_active_managers(exclude_id=manager.id)

    async def reassign_subordinate(
        self,
        manager_telegram_id: int,
        employee_id: int,
        new_manager_id: int,
    ) -> tuple[User, User]:
        """Move an employee to another active manager. Open expenses stay with old cards.

        Returns ``(employee, new_manager)``.
        """
        manager = await self.verify_manager(manager_telegram_id)
        employee = await self._users.get_by_id(employee_id)
        if (
            employee is None
            or employee.manager_id != manager.id
            or employee.role != UserRole.EMPLOYEE
        ):
            raise StaffMemberNotFoundError("subordinate is not available to reassign")
        new_manager = await self._users.get_by_id(new_manager_id)
        if (
            new_manager is None
            or new_manager.id == manager.id
            or new_manager.role != UserRole.MANAGER
            or not new_manager.is_active
        ):
            raise StaffMemberNotFoundError("target manager is not available")
        await self._users.set_manager(employee, new_manager.id)
        return employee, new_manager

    async def link_planfix_user(self, manager_telegram_id: int, planfix_user_id: int) -> User:
        """Bind the manager's local account to a Planfix user id."""
        manager = await self.verify_manager(manager_telegram_id)
        existing = await self._users.get_by_planfix_user_id(planfix_user_id)
        if existing is not None and existing.id != manager.id:
            raise PlanfixLinkConflictError("planfix user already linked")
        await self._users.link_planfix_user(manager, planfix_user_id)
        return manager

    async def verify_manager(self, telegram_id: int) -> User:
        """Return the active manager identified by a Telegram ID."""
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None or not user.is_active or user.role != UserRole.MANAGER:
            raise ManagerRequiredError("active manager required")
        return user

    async def verify_employee(self, telegram_id: int) -> User:
        """Return the active employee identified by a Telegram ID."""
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None or not user.is_active or user.role != UserRole.EMPLOYEE:
            raise EmployeeRequiredError("active employee required")
        return user


def _split_name(value: str) -> tuple[str, str]:
    parts = value.split(maxsplit=1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("full name must include first and last names")
    return parts[0], parts[1]


__all__ = [
    "AlreadyRegisteredError",
    "EmployeeRequiredError",
    "InviteNotFoundError",
    "InviteUnavailableError",
    "InvitedRegistration",
    "ManagerRequiredError",
    "PeopleService",
    "PlanfixLinkConflictError",
    "StaffMemberNotFoundError",
    "StaffOverview",
]
