from aiogram.fsm.state import State, StatesGroup


class OwnerRegistration(StatesGroup):
    waiting_for_name = State()


class EmployeeRegistration(StatesGroup):
    waiting_for_name = State()


class ExpenseSubmission(StatesGroup):
    """FSM for photo and no-receipt expense flows."""

    awaiting_qr_choice = State()
    manual_amount = State()
    manual_date = State()
    category = State()
    direction = State()
    comment = State()
    confirm = State()
    edit_pick = State()
    edit_amount = State()
    edit_date = State()
    edit_comment = State()
    no_receipt_amount = State()
    no_receipt_date = State()
    no_receipt_comment = State()
    no_receipt_proof = State()
    replace_confirm = State()
