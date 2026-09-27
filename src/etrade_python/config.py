"""Validated settings; dotenv loading is always explicit."""

from typing import Any

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from etrade_python.enums import Environment
from etrade_python.exceptions import ETradeValidationError


class ETradeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ETRADE_", env_file=None, extra="ignore", frozen=True, hide_input_in_errors=True
    )

    consumer_key: SecretStr = Field(repr=False)
    consumer_secret: SecretStr = Field(repr=False)
    environment: Environment = Environment.SANDBOX
    request_timeout_seconds: float = Field(default=30.0, gt=0, allow_inf_nan=False)
    inactivity_buffer_seconds: int = Field(default=300, ge=0, lt=7200)

    def __init__(self, **values: Any) -> None:
        # Do not expose Pydantic error inputs through the normal constructor.
        try:
            super().__init__(**values)
        except ValidationError as exc:
            fields = sorted(
                {
                    str(part)
                    for error in exc.errors(include_input=False, include_context=False)
                    for part in error["loc"]
                    if part in type(self).model_fields
                }
            )
            raise ETradeValidationError("Invalid E*TRADE settings: " + ", ".join(fields)) from None

    @field_validator("consumer_key", "consumer_secret")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A nonempty credential is required")
        return value
