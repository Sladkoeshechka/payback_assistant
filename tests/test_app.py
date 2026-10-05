from payback.bot.app import create_dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

def test_create_dispatcher() -> None:
    dispatcher = create_dispatcher()
    assert isinstance(dispatcher.storage, MemoryStorage)
