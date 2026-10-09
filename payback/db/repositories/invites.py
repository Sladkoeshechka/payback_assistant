from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payback.db.models import Invite, UserRole


class InvitesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        code: str,
        role: UserRole,
        created_by_id: int,
        expires_at: datetime,
    ) -> Invite:
        invite = Invite(
            code=code,
            role=role,
            created_by_id=created_by_id,
            expires_at=expires_at,
        )
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def get_by_code(self, code: str) -> Invite | None:
        return await self._session.scalar(select(Invite).where(Invite.code == code))

    async def get_active_by_code(self, code: str, now: datetime) -> Invite | None:
        return await self._session.scalar(
            select(Invite).where(
                Invite.code == code,
                Invite.expires_at > now,
                Invite.used_at.is_(None),
                Invite.revoked_at.is_(None),
            )
        )

    async def get_by_id(self, id: int) -> Invite | None:
        return await self._session.scalar(
            select(Invite).where(
                Invite.id == id,
            )
        )

    async def list_active_for_creator(self, creator_id: int, now: datetime) -> list[Invite]:
        result = await self._session.scalars(
            select(Invite)
            .where(
                Invite.created_by_id == creator_id,
                Invite.expires_at > now,
                Invite.used_at.is_(None),
                Invite.revoked_at.is_(None),
            )
            .order_by(Invite.expires_at)
        )
        return list(result)

    async def consume(self, invite: Invite, user_id: int, used_at: datetime) -> None:
        invite.used_by_id = user_id
        invite.used_at = used_at
        await self._session.flush()

    async def revoke(self, invite: Invite, revoked_at: datetime) -> None:
        invite.revoked_at = revoked_at
        await self._session.flush()
