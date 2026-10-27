from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payback.config import Settings
from payback.db.models import ExpenseStatus, User, UserRole
from payback.db.repositories.expenses import ExpensesRepo
from payback.db.repositories.users import UsersRepo
from payback.services.submission import flush_pending_submissions
from payback.services.draft import SubmissionDraft
from payback.services.fakes import FakeNotifier, FakePlanfix
from payback.services.submission import SubmissionService


async def _people(session: AsyncSession) -> tuple[User, User]:
    users = UsersRepo(session)
    manager = await users.create(
        telegram_id=1000,
        first_name="Grace",
        last_name="Hopper",
        role=UserRole.MANAGER,
    )
    await users.link_planfix_user(manager, 3)
    employee = await users.create(
        telegram_id=1001,
        first_name="Ada",
        last_name="Lovelace",
        role=UserRole.EMPLOYEE,
        manager_id=manager.id,
    )
    await session.commit()
    return manager, employee


def _draft(**overrides: object) -> SubmissionDraft:
    values: dict[str, object] = {
        "amount": Decimal("1250.00"),
        "purchase_date": date(2026, 9, 28),
        "category_id": 7,
        "category_name": "Материалы",
        "no_receipt": False,
        "fn": "9282440300671549",
        "fd": "12345",
        "fp": "67890",
        "telegram_file_id": "tg-file-1",
        "image_bytes": b"jpeg-bytes",
        "qr_locked": True,
    }
    values.update(overrides)
    return SubmissionDraft(**values)  # type: ignore[arg-type]


async def test_flush_pending_submissions_after_planfix_recovers(
    env: dict[str, str], session: AsyncSession, db_engine
) -> None:
    manager, employee = await _people(session)
    failing = FakePlanfix(fail_on="create_task")
    notifier = FakeNotifier()
    fields = Settings().planfix.fields
    service = SubmissionService(ExpensesRepo(session), failing, notifier, fields)
    partial = await service.submit(_draft(), employee=employee, manager=manager)
    await session.commit()
    expense_id = partial.id
    assert partial.status is ExpenseStatus.PENDING_SUBMISSION

    healthy = FakePlanfix()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def download(_file_id: str) -> bytes:
        return b"jpeg-bytes"

    flushed = await flush_pending_submissions(
        session_factory,
        planfix=healthy,
        notifier=notifier,
        field_ids=fields,
        download_file=download,
    )

    assert flushed == 1
    async with session_factory() as check:
        row = await ExpensesRepo(check).get_by_id(expense_id)
        assert row is not None
        assert row.status is ExpenseStatus.PENDING
        assert row.planfix_task_id is not None
        task_id = row.planfix_task_id
    assert notifier.employee_texts
    assert str(task_id) in notifier.employee_texts[0]["text"]
