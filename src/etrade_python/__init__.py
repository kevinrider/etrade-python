"""Unofficial async E*TRADE client. No MCP integration or dependencies."""

from etrade_python.client import ETradeClient
from etrade_python.config import ETradeSettings
from etrade_python.enums import Environment
from etrade_python.exceptions import (
    AuthenticationRequired,
    AuthorizationExpired,
    ETradeApiError,
    ETradeAuthenticationError,
    ETradeError,
    ETradeHttpAuthenticationError,
    ETradeNotFoundError,
    ETradeOrderError,
    ETradeRateLimitError,
    ETradeResponseError,
    ETradeTransportError,
    ETradeUnavailableError,
    ETradeValidationError,
)

__version__ = "0.1.0.dev0"
__all__ = [
    "AuthenticationRequired",
    "AuthorizationExpired",
    "ETradeApiError",
    "ETradeAuthenticationError",
    "ETradeClient",
    "ETradeError",
    "ETradeHttpAuthenticationError",
    "ETradeNotFoundError",
    "ETradeOrderError",
    "ETradeRateLimitError",
    "ETradeResponseError",
    "ETradeSettings",
    "ETradeTransportError",
    "ETradeUnavailableError",
    "ETradeValidationError",
    "Environment",
]
