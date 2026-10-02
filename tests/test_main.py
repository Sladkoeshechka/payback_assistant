import json

import pytest
from pydantic import ValidationError

from payback.config import Settings, get_settings
from payback.main import EXIT_BAD_CONFIG, describe, format_config_errors, main


@pytest.fixture(autouse=True)
def _fresh_settings_cache() -> None:
    """get_settings caches for the process; tests must not inherit each other's."""
    get_settings.cache_clear()


def test_startup_line_is_json_without_secrets(
    env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main() == 0

    line = json.loads(capsys.readouterr().out.strip())
    assert line["message"] == "payback starting"
    assert line["planfix_account"] == "https://example.planfix.ru"
    assert line["planfix_object_id"] == 17
    for secret in ("111:test-bot-token", "test-webhook-secret", "test-planfix-token"):
        assert secret not in json.dumps(line)


def test_describe_reports_configuration_without_secrets(env: dict[str, str]) -> None:
    facts = describe(Settings())

    assert facts["database"] == "sqlite+aiosqlite"
    assert facts["proxy"] is False
    assert "test-planfix-token" not in json.dumps(facts)


def test_incomplete_environment_is_refused_with_the_variable_name(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PLANFIX_STATUS_APPROVED")

    assert main() == EXIT_BAD_CONFIG

    captured = capsys.readouterr()
    assert "PLANFIX_STATUS_APPROVED" in captured.err
    assert "cannot start" in captured.err
    assert captured.out == ""


def test_format_config_errors_lists_every_problem(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_TOKEN")
    monkeypatch.setenv("MAX_RECEIPT_AGE_DAYS", "0")

    with pytest.raises(ValidationError) as caught:
        Settings()

    rendered = format_config_errors(caught.value)
    assert "BOT_TOKEN" in rendered
    assert "MAX_RECEIPT_AGE_DAYS" in rendered
    assert ".env.example" in rendered
