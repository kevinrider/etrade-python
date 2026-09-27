"""Credential models for OAuth lifecycle state."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class RequestToken(BaseModel):
    """Temporary token used only during the browser authorization flow."""

    model_config = ConfigDict(frozen=True)

    oauth_token: SecretStr = Field(repr=False)
    oauth_token_secret: SecretStr = Field(repr=False)
    oauth_callback_confirmed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("oauth_token", "oauth_token_secret")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A nonempty OAuth token value is required")
        return value


class ETradeCredentials(BaseModel):
    """Persisted access-token credentials and lifecycle timestamps."""

    model_config = ConfigDict(frozen=True)

    access_token: SecretStr = Field(repr=False)
    access_token_secret: SecretStr = Field(repr=False)
    acquired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    renewed_at: datetime | None = None

    @field_validator("access_token", "access_token_secret")
    @classmethod
    def nonempty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A nonempty OAuth credential is required")
        return value

    @field_validator("acquired_at", "last_used_at", "renewed_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Credential timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def with_last_used(self, when: datetime) -> "ETradeCredentials":
        return self.model_copy(update={"last_used_at": when.astimezone(UTC)})

    def with_renewal(self, when: datetime) -> "ETradeCredentials":
        normalized = when.astimezone(UTC)
        return self.model_copy(update={"last_used_at": normalized, "renewed_at": normalized})


class AuthorizationUrl(BaseModel):
    """Browser URL for authorizing a request token."""

    model_config = ConfigDict(frozen=True)

    url: str
    request_token: RequestToken


class RenewalResult(BaseModel):
    """Result of a successful E*TRADE access-token renewal."""

    model_config = ConfigDict(frozen=True)

    credentials: ETradeCredentials
    message: str


class RevocationResult(BaseModel):
    """Result of a successful E*TRADE access-token revocation."""

    model_config = ConfigDict(frozen=True)

    revoked: bool
    message: str
