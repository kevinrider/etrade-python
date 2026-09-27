"""Keep HTTPX's automatic URL/wire logs out of SDK request diagnostics."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

_SENSITIVE_EXCHANGE: ContextVar[bool] = ContextVar("etrade_sensitive_exchange", default=False)
_HTTP_LOGGERS = (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
)


class _ExchangeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # This affects only the current task's SDK exchange, not unrelated clients.
        return not _SENSITIVE_EXCHANGE.get()


_FILTER = _ExchangeFilter()


@contextmanager
def private_http_exchange() -> Generator[None, None, None]:
    for name in _HTTP_LOGGERS:
        # addFilter is idempotent for the same instance. Do not change log levels
        # or handlers, which are owned by the host application.
        logging.getLogger(name).addFilter(_FILTER)
    token = _SENSITIVE_EXCHANGE.set(True)
    try:
        yield
    finally:
        _SENSITIVE_EXCHANGE.reset(token)
