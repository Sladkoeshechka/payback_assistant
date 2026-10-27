from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import UserRole
from payback.db.repositories.users import UsersRepo
from tests.conftest import RecordingSession


async def test_inactive_user_is_blocked_by_middleware(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    users = UsersRepo(session)
    employee = await users.create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
    )
    await users.set_active(employee, False)
    await session.commit()

    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(settings, async_sessionmaker(db_engine, expire_on_commit=False))

    await dispatcher.feed_raw_update(bot, _message_update(1, 2, "/my"))
    assert getattr(telegram_session.methods[-1], "text", None) == (
        "Ваш доступ отключён. Обратитесь к руководителю."
    )


def _message_update(update_id: int, user_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "David"},
            "text": text,
            "entities": [{"offset": 0, "length": len(text.split()[0]), "type": "bot_command"}],
        },
    }
