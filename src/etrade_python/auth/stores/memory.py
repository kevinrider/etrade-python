"""In-memory credential store."""

import asyncio
from contextlib import AbstractAsyncContextManager

from etrade_python.auth.credentials import ETradeCredentials


class MemoryCredentialStore:
    """Process-local credential store, mainly for tests and temporary sessions."""

    def __init__(self) -> None:
        self._credentials: dict[str, ETradeCredentials] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, namespace: str) -> AbstractAsyncContextManager[None]:
        """Coordinate managers sharing this store instance and event loop."""
        return self._locks.setdefault(namespace, asyncio.Lock())

    async def load(self, profile: str) -> ETradeCredentials | None:
        return self._credentials.get(profile)

    async def save(self, profile: str, credentials: ETradeCredentials) -> None:
        self._credentials[profile] = credentials

    async def delete(self, profile: str) -> None:
        self._credentials.pop(profile, None)
