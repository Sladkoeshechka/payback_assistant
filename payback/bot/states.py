from aiogram.fsm.state import State, StatesGroup


class OwnerRegistration(StatesGroup):
    waiting_for_name = State()


class EmployeeRegistration(StatesGroup):
    waiting_for_name = State()
