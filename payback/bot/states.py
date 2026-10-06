from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_for_name = State()
