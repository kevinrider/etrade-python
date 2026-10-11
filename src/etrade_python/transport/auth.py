"""Request authentication and optional confirmed-usage notification."""

from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx


class RequestAuthenticator(Protocol):
    async def authenticate(self, request: httpx.Request) -> Callable[[], Awaitable[None]] | None:
        """Attach auth headers in place, using fresh signing state for each attempt.

        Must not change the method, URL, or body. Implementations must mask their own repr
        and must not log secrets. May return a request-local callback to record usage
        after a completed 2xx exchange. Returning None requires no notification.
        """
        ...
