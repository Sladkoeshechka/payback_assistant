from decimal import Decimal
from urllib.parse import unquote, urlparse

import pytest
from pydantic import ValidationError

from payback.config import Settings


def test_reads_the_env_names_documented_in_the_spec(env: dict[str, str]) -> None:
    settings = Settings()

    assert settings.owner_telegram_id == 100500
    assert settings.planfix.object_id == 17
    # Prefixed variables land in the nested models.
    assert settings.planfix.fields.amount == 141074
    assert settings.planfix.fields.payment_date == 141384
    assert settings.planfix.statuses.approved == 103
    assert settings.planfix.statuses.reimbursed == 108


def test_defaults_apply_when_optional_variables_are_absent(env: dict[str, str]) -> None:
    settings = Settings()

    assert settings.max_amount == Decimal("100000")
    assert settings.max_receipt_age_days == 90
    assert settings.allow_no_receipt is True
    assert settings.no_receipt_max_amount is None
    assert settings.dev_mode is False
    assert settings.allow_dev_mode is False
    assert settings.proxy_url is None


def test_prod_like_env_without_dev_mode_loads(env: dict[str, str]) -> None:
    """Default settings load with DEV_MODE off."""
    settings = Settings()
    assert settings.dev_mode is False
    assert settings.allow_dev_mode is False


def test_dev_mode_without_allow_is_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEV_MODE without ALLOW_DEV_MODE must not load."""
    monkeypatch.setenv("DEV_MODE", "true")

    with pytest.raises(ValidationError, match="ALLOW_DEV_MODE"):
        Settings()


def test_dev_mode_with_allow_loads(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.setenv("ALLOW_DEV_MODE", "true")

    settings = Settings()
    assert settings.dev_mode is True
    assert settings.allow_dev_mode is True


def test_missing_variable_is_reported_by_name(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PLANFIX_FIELD_AMOUNT")

    with pytest.raises(ValidationError, match="PLANFIX_FIELD_AMOUNT"):
        Settings()


def test_secrets_are_not_exposed_by_repr(env: dict[str, str]) -> None:
    settings = Settings()

    assert "test-planfix-token" not in repr(settings)
    assert "test-bot-token" not in repr(settings)
    assert settings.planfix.api_token.get_secret_value() == "test-planfix-token"
    expected = {
        "111:test-bot-token",
        "test-webhook-secret",
        "test-planfix-token",
    }
    db_password = urlparse(env["DATABASE_URL"]).password
    if db_password:
        expected.add(unquote(db_password))
    assert set(settings.secrets()) == expected


def test_database_url_password_is_included_in_secrets(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://payback:s3cret%21pass@db.example/payback",
    )

    assert "s3cret!pass" in Settings().secrets()


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("WEBHOOK_SECRET", ""),
        ("WEBHOOK_SECRET", "   "),
        ("BOT_TOKEN", ""),
        ("PLANFIX_API_TOKEN", ""),
    ],
)
def test_blank_required_secrets_are_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError, match="must not be empty"):
        Settings()


def test_rest_base_url_tolerates_a_trailing_slash(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLANFIX_ACCOUNT", "https://example.planfix.ru/")

    assert Settings().planfix.rest_base_url == "https://example.planfix.ru/rest"


def test_account_without_scheme_is_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLANFIX_ACCOUNT", "example.planfix.ru")

    with pytest.raises(ValidationError, match="must include the scheme"):
        Settings()


def test_duplicate_status_ids_are_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two statuses sharing an id would make transitions ambiguous."""
    monkeypatch.setenv("PLANFIX_STATUS_REJECTED", env["PLANFIX_STATUS_APPROVED"])

    with pytest.raises(ValidationError, match="PLANFIX_STATUS_"):
        Settings()


def test_duplicate_field_ids_are_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards against pointing two fields at 141370 and its undeletable twin."""
    monkeypatch.setenv("PLANFIX_FIELD_DIRECTION", env["PLANFIX_FIELD_CATEGORY"])

    with pytest.raises(ValidationError, match="PLANFIX_FIELD_"):
        Settings()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_optional_values_mean_unset(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """An empty NO_RECEIPT_MAX_AMOUNT means "no cap"."""
    monkeypatch.setenv("NO_RECEIPT_MAX_AMOUNT", blank)
    monkeypatch.setenv("PROXY_URL", blank)

    settings = Settings()

    assert settings.no_receipt_max_amount is None
    assert settings.proxy_url is None


def test_no_receipt_cap_above_max_amount_is_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_AMOUNT", "5000")
    monkeypatch.setenv("NO_RECEIPT_MAX_AMOUNT", "6000")

    with pytest.raises(ValidationError, match="NO_RECEIPT_MAX_AMOUNT"):
        Settings()


@pytest.mark.parametrize(
    ("variable", "value"),
    [("MAX_AMOUNT", "0"), ("MAX_AMOUNT", "-1"), ("MAX_RECEIPT_AGE_DAYS", "0")],
)
def test_non_positive_limits_are_rejected(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        Settings()
