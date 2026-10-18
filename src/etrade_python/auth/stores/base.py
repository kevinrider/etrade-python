"""Credential store protocol."""

from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable

from etrade_python.auth.credentials import ETradeCredentials


class CredentialStore(Protocol):
    """Async persistence boundary for OAuth credentials."""

    async def load(self, profile: str) -> ETradeCredentials | None:
        """Load credentials for a profile, returning None when absent."""

    async def save(self, profile: str, credentials: ETradeCredentials) -> None:
        """Persist credentials for a profile."""

    async def delete(self, profile: str) -> None:
        """Delete credentials for a profile."""


@runtime_checkable
class CoordinatedCredentialStore(CredentialStore, Protocol):
    """Optional transaction lock shared by all users of a credential namespace.

    SessionManager holds this lock across complete lifecycle operations. Store
    methods must not reacquire it. Direct store users must explicitly acquire it
    around read/modify/write sequences. Locks need not be reentrant.
    """

    def lock(self, namespace: str) -> AbstractAsyncContextManager[None]:
        """Exclusively coordinate a namespace, releasing ownership on exit."""
        ...
