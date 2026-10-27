"""Settings read from environment variables.

The Planfix object, field and status ids add up to ~20 variables. They are grouped
into nested settings models that each read their own prefix, so the environment
names stay exactly as documented (``PLANFIX_FIELD_AMOUNT``) while code
reads ``settings.planfix.fields.amount``.

Two PlanFix quirks shape this module:

* Status **names differ between accounts** — e.g. id 108 may be "компенсация завершена"
  on one account and "Компенсировано" on another — so every status is addressed by id.
  The webhook body carries a name, and the bot never trusts it.
* Accounts can carry **duplicate custom fields** (undeletable twins). A name-based
  field lookup would be ambiguous, so field ids are always configured explicitly.
"""

from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = ".env"


def _env(name: str) -> Any:
    """Declare a required setting bound to an explicit environment variable.

    Spelling the variable out rather than deriving it from an ``env_prefix`` is what
    makes a misconfiguration readable: pydantic reports the missing key as
    ``PLANFIX_FIELD_AMOUNT`` instead of ``PlanfixFieldIds.amount``, which is what the
    startup check is supposed to print.
    """
    return Field(validation_alias=name)


class PlanfixFieldIds(BaseSettings):
    """Ids of the custom task fields making up the "Расход" card."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    amount: int = _env("PLANFIX_FIELD_AMOUNT")
    purchase_date: int = _env("PLANFIX_FIELD_PURCHASE_DATE")
    category: int = _env("PLANFIX_FIELD_CATEGORY")
    direction: int = _env("PLANFIX_FIELD_DIRECTION")
    employee: int = _env("PLANFIX_FIELD_EMPLOYEE")
    fn: int = _env("PLANFIX_FIELD_FN")
    fd: int = _env("PLANFIX_FIELD_FD")
    fp: int = _env("PLANFIX_FIELD_FP")
    no_receipt: int = _env("PLANFIX_FIELD_NO_RECEIPT")
    payment_date: int = _env("PLANFIX_FIELD_PAYMENT_DATE")

    def all_ids(self) -> list[int]:
        return [getattr(self, name) for name in type(self).model_fields]

    @model_validator(mode="after")
    def ids_must_be_distinct(self) -> "PlanfixFieldIds":
        _reject_duplicates(self.all_ids(), "PLANFIX_FIELD_*")
        return self


class PlanfixStatusIds(BaseSettings):
    """Ids of the "Расход" status set."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    pending: int = _env("PLANFIX_STATUS_PENDING")
    clarification: int = _env("PLANFIX_STATUS_CLARIFICATION")
    approved: int = _env("PLANFIX_STATUS_APPROVED")
    rejected: int = _env("PLANFIX_STATUS_REJECTED")
    needs_revision: int = _env("PLANFIX_STATUS_NEEDS_REVISION")
    to_pay: int = _env("PLANFIX_STATUS_TO_PAY")
    reimbursed: int = _env("PLANFIX_STATUS_REIMBURSED")

    def all_ids(self) -> list[int]:
        return [getattr(self, name) for name in type(self).model_fields]

    @model_validator(mode="after")
    def ids_must_be_distinct(self) -> "PlanfixStatusIds":
        _reject_duplicates(self.all_ids(), "PLANFIX_STATUS_*")
        return self


class PlanfixSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    account: str = _env("PLANFIX_ACCOUNT")
    api_token: SecretStr = _env("PLANFIX_API_TOKEN")
    object_id: int = _env("PLANFIX_OBJECT_ID")

    fields: PlanfixFieldIds = Field(default_factory=lambda: PlanfixFieldIds())
    statuses: PlanfixStatusIds = Field(default_factory=lambda: PlanfixStatusIds())

    @field_validator("api_token")
    @classmethod
    def api_token_must_be_non_empty(cls, value: SecretStr) -> SecretStr:
        return _reject_blank_secret(value, "PLANFIX_API_TOKEN")

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError(
                "PLANFIX_ACCOUNT must include the scheme, e.g. https://acme.planfix.ru"
            )
        return value

    @property
    def rest_base_url(self) -> str:
        """Base URL of the REST API."""
        return f"{self.account}/rest"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    bot_token: SecretStr
    owner_telegram_id: int

    proxy_url: str | None = None
    """Optional proxy for the Telegram API, for hosts without direct access."""

    webhook_secret: SecretStr
    database_url: str = "postgresql+asyncpg://payback:payback@127.0.0.1:5432/payback"

    @field_validator("bot_token", "webhook_secret")
    @classmethod
    def required_secrets_must_be_non_empty(
        cls, value: SecretStr, info: ValidationInfo
    ) -> SecretStr:
        return _reject_blank_secret(value, (info.field_name or "secret").upper())

    max_amount: Decimal = Decimal("100000")
    max_receipt_age_days: int = 90
    allow_no_receipt: bool = True
    no_receipt_max_amount: Decimal | None = None

    dev_mode: bool = False
    """When true (and ALLOW_DEV_MODE), PlanFix outages fall back to FakePlanFix."""

    allow_dev_mode: bool = False
    """Explicit non-prod admit. Required if DEV_MODE=true."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    planfix: PlanfixSettings = Field(default_factory=lambda: PlanfixSettings())

    @field_validator("proxy_url", "no_receipt_max_amount", mode="before")
    @classmethod
    def blank_means_unset(cls, value: object) -> object:
        """An empty variable means "not set".

        Empty NO_RECEIPT_MAX_AMOUNT means "no cap", and
        .env files carry empty values far more often than missing lines.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("max_amount", "no_receipt_max_amount")
    @classmethod
    def amount_must_be_positive(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("amount limits must be greater than 0")
        return value

    @field_validator("max_receipt_age_days")
    @classmethod
    def age_must_be_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_RECEIPT_AGE_DAYS must be greater than 0")
        return value

    @model_validator(mode="after")
    def no_receipt_limit_within_max(self) -> "Settings":
        if self.no_receipt_max_amount is not None and self.no_receipt_max_amount > self.max_amount:
            raise ValueError("NO_RECEIPT_MAX_AMOUNT must not exceed MAX_AMOUNT")
        return self

    @model_validator(mode="after")
    def dev_mode_requires_explicit_allow(self) -> "Settings":
        if self.dev_mode and not self.allow_dev_mode:
            raise ValueError(
                "DEV_MODE=true requires ALLOW_DEV_MODE=true "
                "(refuses to start without an explicit non-prod admit)"
            )
        return self

    def secrets(self) -> list[str]:
        """Every secret value, for registration with the log redactor."""
        values = [
            self.bot_token.get_secret_value(),
            self.webhook_secret.get_secret_value(),
            self.planfix.api_token.get_secret_value(),
        ]
        db_password = _database_password(self.database_url)
        if db_password is not None:
            values.append(db_password)
        return values


def _database_password(database_url: str) -> str | None:
    """Return the URL-decoded DB password, if the URL carries one."""
    password = urlparse(database_url).password
    if password is None or password == "":
        return None
    return unquote(password)


def _reject_blank_secret(value: SecretStr, name: str) -> SecretStr:
    if not value.get_secret_value().strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _reject_duplicates(ids: list[int], group: str) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError(
            f"{group} ids must be distinct; two entries sharing an id would make "
            "field writes or status transitions ambiguous"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once."""
    return Settings()


__all__ = [
    "PlanfixFieldIds",
    "PlanfixSettings",
    "PlanfixStatusIds",
    "Settings",
    "get_settings",
]
