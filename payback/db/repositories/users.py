from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payback.db.models import User, UserRole


class UsersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._session.scalar(select(User).where(User.telegram_id == telegram_id))

    async def create(
        self,
        *,
        telegram_id: int,
        first_name: str,
        last_name: str,
        role: UserRole,
        manager_id: int | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            role=role,
            manager_id=manager_id,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        first_name: str,
        last_name: str,
        role: UserRole,
        manager_id: int | None = None,
    ) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            return user, False
        return (
            await self.create(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                role=role,
                manager_id=manager_id,
            ),
            True,
        )

    async def list_active_subordinates(self, manager_id: int) -> list[User]:
        result = await self._session.scalars(
            select(User)
            .where(User.manager_id == manager_id, User.is_active.is_(True))
            .order_by(User.last_name, User.first_name, User.id)
        )
        return list(result)

    async def set_active(self, user: User, is_active: bool) -> None:
        user.is_active = is_active
        await self._session.flush()

    async def link_planfix_user(self, user: User, planfix_user_id: int | None) -> None:
        user.planfix_user_id = planfix_user_id
        await self._session.flush()
