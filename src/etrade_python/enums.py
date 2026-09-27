"""Configuration enums shared across API domains."""

from enum import StrEnum


class Environment(StrEnum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"

    @property
    def api_base_url(self) -> str:
        if self is Environment.PRODUCTION:
            return "https://api.etrade.com"
        return "https://apisb.etrade.com"


# E*TRADE uses the same OAuth server for sandbox and production keys.
OAUTH_BASE_URL = "https://api.etrade.com"
AUTHORIZATION_URL = "https://us.etrade.com/e/t/etws/authorize"
