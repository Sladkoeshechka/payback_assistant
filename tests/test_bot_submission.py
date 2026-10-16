from datetime import date
from decimal import Decimal
from pathlib import Path

from aiogram import Bot
from conftest import RecordingSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payback.bot.app import create_dispatcher
from payback.config import Settings
from payback.db.models import Expense, ExpenseStatus, User, UserRole
from payback.db.repositories.users import UsersRepo
from payback.planfix.directories import DirectoryCache
from payback.planfix.models import PlanfixDirectoryEntry, PlanfixSchema
from payback.services.fakes import FakeNotifier, FakePlanfix

_RECEIPT = Path(__file__).parent / "fixtures" / "receipts" / "valid-receipt.jpg"
_CATEGORY_DIR = 10
_DIRECTION_DIR = 20


async def test_photo_submission_reaches_planfix(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, employee = await _people(session, settings)
    planfix, cache, schema, notifier = _planfix_stack()
    telegram_session = RecordingSession(download_bytes=_RECEIPT.read_bytes())
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        directory_cache=cache,
        planfix_schema=schema,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(
        bot, _photo_update(1, employee.telegram_id, file_id="receipt-file")
    )
    assert any(
        getattr(method, "text", None) == "Распознаю чек…" for method in telegram_session.methods
    )
    assert any(
        getattr(method, "text", None) and "Чек на" in getattr(method, "text", "")
        for method in telegram_session.methods
    )

    await dispatcher.feed_raw_update(bot, _callback_update(2, employee.telegram_id, "sub:cat:7"))
    await dispatcher.feed_raw_update(bot, _callback_update(3, employee.telegram_id, "sub:dir:2"))
    await dispatcher.feed_raw_update(
        bot, _callback_update(4, employee.telegram_id, "sub:skip_comment")
    )
    assert any(
        getattr(method, "text", None) and "Заявка на расход" in getattr(method, "text", "")
        for method in telegram_session.methods
    )

    await dispatcher.feed_raw_update(bot, _callback_update(5, employee.telegram_id, "sub:send"))
    assert any(
        getattr(method, "text", None) == "Заявка №100 отправлена на согласование."
        for method in telegram_session.methods
    )

    expense = (await session.scalars(select(Expense))).one()
    assert expense.status is ExpenseStatus.PENDING
    assert expense.planfix_task_id == 100
    assert expense.planfix_file_id == 1000
    assert expense.employee_id == employee.id
    assert expense.amount == Decimal("890.00")
    assert expense.purchase_date == date(2026, 10, 2)
    assert expense.fn == "7284440500112233"
    assert planfix.create_calls == 1
    assert planfix.upload_calls == 1
    assert planfix.attach_calls == 1
    assert len(notifier.messages) == 1
    assert notifier.messages[0]["manager_id"] == manager.id


async def test_no_receipt_submission(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    manager, employee = await _people(session, settings)
    planfix, cache, schema, notifier = _planfix_stack()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        directory_cache=cache,
        planfix_schema=schema,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(bot, _message_update(1, employee.telegram_id, "/noreceipt"))
    assert getattr(telegram_session.methods[-1], "text", None) == "Введите сумму покупки."

    await dispatcher.feed_raw_update(bot, _message_update(2, employee.telegram_id, "150,50"))
    await dispatcher.feed_raw_update(bot, _message_update(3, employee.telegram_id, "01.10.2026"))
    await dispatcher.feed_raw_update(bot, _callback_update(4, employee.telegram_id, "sub:cat:7"))
    await dispatcher.feed_raw_update(bot, _callback_update(5, employee.telegram_id, "sub:dir:none"))
    await dispatcher.feed_raw_update(
        bot, _message_update(6, employee.telegram_id, "Такси до объекта, чек утерян")
    )
    await dispatcher.feed_raw_update(
        bot, _callback_update(7, employee.telegram_id, "sub:proof:skip")
    )
    await dispatcher.feed_raw_update(bot, _callback_update(8, employee.telegram_id, "sub:send"))

    assert any(
        getattr(method, "text", None) == "Заявка №100 отправлена на согласование."
        for method in telegram_session.methods
    )
    expense = (await session.scalars(select(Expense))).one()
    assert expense.no_receipt is True
    assert expense.amount == Decimal("150.50")
    assert expense.comment == "Такси до объекта, чек утерян"
    assert expense.direction_id is None
    assert planfix.upload_calls == 0
    assert len(notifier.messages) == 1
    assert manager.id == notifier.messages[0]["manager_id"]


async def test_cancel_clears_draft(
    env: dict[str, str], db_engine: AsyncEngine, session: AsyncSession
) -> None:
    settings = Settings()
    _, employee = await _people(session, settings)
    planfix, cache, schema, notifier = _planfix_stack()
    telegram_session = RecordingSession()
    bot = Bot(token=settings.bot_token.get_secret_value(), session=telegram_session)
    dispatcher = create_dispatcher(
        settings,
        async_sessionmaker(db_engine, expire_on_commit=False),
        planfix=planfix,
        directory_cache=cache,
        planfix_schema=schema,
        notifier=notifier,
    )

    await dispatcher.feed_raw_update(bot, _message_update(1, employee.telegram_id, "/noreceipt"))
    await dispatcher.feed_raw_update(bot, _message_update(2, employee.telegram_id, "/cancel"))
    text = getattr(telegram_session.methods[-1], "text", None)
    assert text is not None
    assert "Заявка отменена." in text
    assert "/my" in text


async def _people(session: AsyncSession, settings: Settings) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=settings.owner_telegram_id,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    employee = await users.create(
        telegram_id=2,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, employee


def _planfix_stack() -> tuple[FakePlanfix, DirectoryCache, PlanfixSchema, FakeNotifier]:
    planfix = FakePlanfix(
        directory_entries={
            _CATEGORY_DIR: [PlanfixDirectoryEntry(key=7, name="Материалы")],
            _DIRECTION_DIR: [PlanfixDirectoryEntry(key=2, name="Ленина 5")],
        }
    )
    cache = DirectoryCache(planfix)
    schema = PlanfixSchema(
        category_directory_id=_CATEGORY_DIR,
        direction_directory_id=_DIRECTION_DIR,
    )
    return planfix, cache, schema, FakeNotifier()


def _message_update(update_id: int, user_id: int, text: str) -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": update_id,
        "date": 1_700_000_000,
        "chat": {"id": user_id, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
        "text": text,
    }
    if text.startswith("/"):
        message["entities"] = [{"offset": 0, "length": len(text.split()[0]), "type": "bot_command"}]
    return {"update_id": update_id, "message": message}


def _callback_update(update_id: int, user_id: int, data: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": str(update_id),
            "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
            "chat_instance": "test",
            "data": data,
            "message": {
                "message_id": update_id,
                "date": 1_700_000_000,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 111, "is_bot": True, "first_name": "Payback"},
                "text": "…",
            },
        },
    }


def _photo_update(update_id: int, user_id: int, *, file_id: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
            "photo": [
                {
                    "file_id": file_id,
                    "file_unique_id": "uid",
                    "width": 100,
                    "height": 100,
                    "file_size": 10,
                }
            ],
        },
    }
