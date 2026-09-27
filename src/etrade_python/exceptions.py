"""Stable public errors. Never attach raw HTTP requests or responses."""


class ETradeError(Exception):
    """Base class for library failures."""


class ETradeAuthenticationError(ETradeError):
    """Authentication failed or is unavailable."""


class AuthenticationRequired(ETradeAuthenticationError):
    """Human authorization or an authentication provider is required."""


class AuthorizationExpired(ETradeAuthenticationError):
    """The daily authorization has expired."""


class ETradeValidationError(ETradeError):
    """Local settings or request arguments are invalid."""


class ETradeApiError(ETradeError):
    """Broker failure with sanitized diagnostic metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        broker_code: str | None = None,
        broker_message: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.broker_code = broker_code
        self.broker_message = broker_message
        self.request_id = request_id


class ETradeRateLimitError(ETradeApiError):
    """The broker rejected a request because of a rate limit."""


class ETradeNotFoundError(ETradeApiError):
    """The requested resource was not found."""


class ETradeUnavailableError(ETradeApiError):
    """The broker is temporarily unavailable."""


class ETradeOrderError(ETradeApiError):
    """An order operation was rejected."""


class ETradeTransportError(ETradeError):
    """The HTTP exchange failed; a mutation's outcome may be unknown."""


class ETradeResponseError(ETradeApiError):
    """The broker returned an invalid or unexpected response."""


class ETradeHttpAuthenticationError(ETradeAuthenticationError, ETradeApiError):
    """An HTTP authentication rejection, including sanitized broker metadata."""
