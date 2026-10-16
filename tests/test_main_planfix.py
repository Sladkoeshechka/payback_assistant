from payback.main import offline_planfix_stack
from payback.services.fakes import FakePlanfix


def test_offline_planfix_stack_has_sample_directories() -> None:
    planfix, schema = offline_planfix_stack()
    assert isinstance(planfix, FakePlanfix)
    assert schema.category_directory_id in planfix.directory_entries
    assert schema.direction_directory_id in planfix.directory_entries
    assert planfix.directory_entries[schema.category_directory_id]
