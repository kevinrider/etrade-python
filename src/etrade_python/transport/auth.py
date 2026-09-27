"""The request authentication boundary; OAuth arrives in milestone 2."""

from typing import Protocol

import httpx


class RequestAuthenticator(Protocol):
    async def authenticate(self, request: httpx.Request) -> None:
        """Attach auth headers in place, using fresh signing state for each attempt.

        Must not change the method, URL, or body. Implementations must mask their own repr
        and must not log secrets. A future SessionManager-backed adapter implements
        this protocol without making the transport depend on a credential store.
        """
        ...
